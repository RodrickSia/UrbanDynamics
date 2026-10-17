"""Run on server 156: deploy origin/main to the existing main Compose project.

Configuration is taken from existing containers, never written to Git or stdout.
The preview remains separate. Existing PostGIS and runtime volumes are retained.
"""
import datetime
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def inspect(name):
    return json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]


def env(container):
    return dict(item.split('=', 1) for item in container['Config']['Env'] if '=' in item)


def update_checkout(bundle):
    if bundle:
        run(['git', 'bundle', 'verify', str(bundle.resolve())], cwd=ROOT)
        run(['git', 'fetch', str(bundle.resolve()), 'HEAD:refs/remotes/origin/main'], cwd=ROOT)
    else:
        run(['git', 'fetch', 'origin'], cwd=ROOT)
    run(['git', 'switch', 'main'], cwd=ROOT)
    run(['git', 'merge', '--ff-only', 'origin/main'], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, help='Verified Git bundle when server GitHub authentication is unavailable')
    parser.add_argument('--frontend-only', action='store_true', help='Update only the web UI; preserve running backend and simulation jobs')
    parser.add_argument('--backend-only', action='store_true', help='Update API and workers while preserving the running frontend')
    args = parser.parse_args()
    if args.frontend_only and args.backend_only:
        parser.error('--frontend-only and --backend-only cannot be used together')
    if ROOT.name != 'UrbanDynamics' or ROOT.parent.name != 'UrbanDynamics':
        raise RuntimeError('Run only from the existing team server checkout')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Server checkout has uncommitted changes')
    if args.frontend_only:
        for name in ['.env', '.env.production.local', 'compose.production-agent.yaml']:
            if not (ROOT / name).is_file():
                raise RuntimeError('Complete the initial deployment before a frontend-only update')
        stamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        backup = ROOT / '.runtime' / ('main-frontend-release-' + stamp)
        backup.mkdir(parents=True, mode=0o700)
        frontend = inspect('urbandynamics-frontend-1')
        tag = 'urbandynamics-rollback-frontend:' + stamp.lower()
        run(['docker', 'tag', frontend['Image'], tag])
        (backup / 'previous-commit.txt').write_text(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True))
        (backup / 'images.json').write_text(json.dumps({'frontend': tag}, indent=2))
        update_checkout(args.bundle)
        compose = ['docker', 'compose', '-p', 'urbandynamics', '--env-file', '.env', '--env-file', '.env.production.local', '-f', 'compose.yaml', '-f', 'compose.production-agent.yaml']
        run(compose + ['config', '--quiet'], cwd=ROOT)
        run(compose + ['build', 'frontend'], cwd=ROOT)
        run(compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', 'frontend'], cwd=ROOT)
        (backup / 'deployed-commit.txt').write_text(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True))
        print(json.dumps({'status': 'deployed', 'scope': 'frontend', 'port': 51873, 'backup': str(backup)}))
        return
    backend = inspect('urbandynamics-backend-1')
    frontend = None if args.backend_only else inspect('urbandynamics-frontend-1')
    preview = inspect('urbandynamics-development-preview-backend-1')
    # Query PostGIS directly so a stopped API container does not prevent its
    # own recovery deployment. Refuse to restart workers during native jobs.
    warehouse = inspect('urbandynamics-postgis-1')
    if not warehouse['State']['Running']:
        raise RuntimeError('PostGIS must be running before deploying the backend')
    warehouse_env = env(warehouse)
    probe = "SELECT count(*) FROM planning_jobs WHERE status IN ('queued','running')"
    active = subprocess.check_output([
        'docker', 'exec', warehouse['Id'], 'psql', '-X', '--set', 'ON_ERROR_STOP=1',
        '--tuples-only', '--no-align', '--username', warehouse_env['POSTGRES_USER'],
        '--dbname', warehouse_env['POSTGRES_DB'], '--command', probe,
    ], text=True)
    if int(active.strip()):
        raise RuntimeError('Wait for active main planning jobs before deploying')
    stamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT / '.runtime' / ('main-release-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    old_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    (backup / 'previous-commit.txt').write_text(old_head + '\n')
    old_images = {}
    old_containers = [('backend', backend)]
    if frontend is not None:
        old_containers.append(('frontend', frontend))
    for service, container in old_containers:
        tag = 'urbandynamics-rollback-' + service + ':' + stamp.lower()
        run(['docker', 'tag', container['Image'], tag])
        old_images[service] = tag
    (backup / 'images.json').write_text(json.dumps(old_images, indent=2))
    for name in ['.env', '.env.production.local', '.env.agent.production.local']:
        source = ROOT / name
        if source.exists():
            dest = backup / name
            dest.write_bytes(source.read_bytes())
            dest.chmod(0o600)
    # The existing Actions workflow removes its generated .env after deployment.
    # Recover only application configuration from the still-existing container.
    base_env = ROOT / '.env'
    if not base_env.exists():
        inherited = {k: v for k, v in env(backend).items() if k.startswith(('WAREHOUSE_', 'GOONG_', 'VITE_', 'BACKEND_', 'TRAFFIC_', 'SIMULATION_', 'PLANNING_', 'SCENARIO_', 'ZONING_')) or k == 'DATA_DIR'}
        # Dedicated backend credentials must not enter the shared worker env.
        inherited.pop('GOONG_REST_API_KEY', None)
        if not inherited.get('WAREHOUSE_PASSWORD'):
            raise RuntimeError('Cannot recover warehouse configuration')
        base_env.write_text(''.join(k + '=' + json.dumps(v) + '\n' for k, v in inherited.items()))
        base_env.chmod(0o600)
    settings = env(preview)
    agent = {key: settings[key] for key in ['OPENAI_API_KEY', 'OPENAI_MODEL', 'GOONG_REST_API_KEY', 'AGENT_ENABLED', 'AGENT_DAILY_MODEL_CALL_LIMIT', 'AGENT_MAX_ROUNDS'] if key in settings}
    if not agent.get('OPENAI_API_KEY') or not agent.get('GOONG_REST_API_KEY'):
        # The web/API deployment can proceed without the optional AI agent.
        # Keep absent provider credentials out of the production env file.
        agent = {'AGENT_ENABLED': '0'}
    target = ROOT / '.env.agent.production.local'
    target.write_text(''.join(k + '=' + v + '\n' for k, v in agent.items()))
    target.chmod(0o600)
    # Reuse only the public tile credential. Model/REST credentials remain backend-only.
    preview_env = ROOT.parent / 'development-preview' / '.env.development.local'
    preview_values = dict(line.split('=', 1) for line in preview_env.read_text().splitlines() if '=' in line and not line.startswith('#'))
    mounted_data = next(m['Source'] for m in backend['Mounts'] if m['Destination'] == '/data')
    datasets = ROOT.parent / 'development-preview' / 'datasets'
    production = {'FRONTEND_PORT': '127.0.0.1:51873', 'VITE_GOONG_MAPTILES_KEY': preview_values['VITE_GOONG_MAPTILES_KEY'], 'VITE_API_BASE_URL': '',
                  'URBANDYNAMICS_DATA_DIR': mounted_data, 'PLANNING_SNAPSHOT_HOST_DIR': str(datasets / 'snapshots'), 'PLANNING_COUNTING_HOST_DIR': str(datasets / 'counting')}
    target = ROOT / '.env.production.local'
    target.write_text(''.join(k + '=' + v + '\n' for k, v in production.items()))
    target.chmod(0o600)
    # Copy the supplementary POI dataset, not preview sessions/plans/job history.
    run(['docker', 'cp', preview['Id'] + ':/runtime/agent-pois', str(backup / 'agent-pois')])
    run(['docker', 'cp', str(backup / 'agent-pois'), backend['Id'] + ':/runtime/agent-pois'])
    if backend['State']['Running']:
        run(['docker', 'exec', '--user', '0', backend['Id'], 'chown', '-R', '10001:10001', '/runtime/agent-pois'])
    else:
        runtime = next(mount for mount in backend['Mounts'] if mount['Destination'] == '/runtime')
        run([
            'docker', 'run', '--rm', '--volume', runtime['Name'] + ':/runtime',
            '--entrypoint', 'chown', backend['Image'], '-R', '10001:10001', '/runtime/agent-pois',
        ])
    update_checkout(args.bundle)
    compose = ['docker', 'compose', '-p', 'urbandynamics', '--env-file', '.env', '--env-file', '.env.production.local', '-f', 'compose.yaml', '-f', 'compose.production-agent.yaml']
    # Validate and build before recreating any live service. Never restart PostGIS.
    run(compose + ['config', '--quiet'], cwd=ROOT)
    build_services = ['backend'] if args.backend_only else ['backend', 'frontend']
    deploy_services = ['backend', 'planning-worker', 'traffic-prediction-worker']
    if not args.backend_only:
        deploy_services.append('frontend')
    run(compose + ['build', *build_services], cwd=ROOT)
    run(compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', *deploy_services], cwd=ROOT)
    (backup / 'deployed-commit.txt').write_text(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True))
    scope = 'backend' if args.backend_only else 'backend-and-frontend'
    print(json.dumps({'status': 'deployed', 'scope': scope, 'port': 51873, 'backup': str(backup)}))


if __name__ == '__main__':
    main()
