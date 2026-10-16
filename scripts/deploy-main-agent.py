"""Run on server 156: deploy origin/main to the existing main Compose project.

Configuration is taken from existing containers, never written to Git or stdout.
The preview remains separate. Existing PostGIS and runtime volumes are retained.
"""
import datetime
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


def main():
    if ROOT.name != 'UrbanDynamics' or ROOT.parent.name != 'UrbanDynamics':
        raise RuntimeError('Run only from the existing team server checkout')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Server checkout has uncommitted changes')
    backend = inspect('urbandynamics-backend-1')
    frontend = inspect('urbandynamics-frontend-1')
    preview = inspect('urbandynamics-development-preview-backend-1')
    # Refuse to restart a worker while a native planning job is in progress.
    probe = "from app.services.simulation.planning.store import transaction\nwith transaction() as db:\n print(db.execute(\"SELECT count(*) FROM planning_jobs WHERE status IN ('queued','running')\").fetchone()[0])"
    active = subprocess.check_output(['docker', 'exec', backend['Id'], 'python', '-c', probe], text=True)
    if int(active.strip()):
        raise RuntimeError('Wait for active main planning jobs before deploying')
    stamp = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT / '.runtime' / ('main-release-' + stamp)
    backup.mkdir(parents=True, mode=0o700)
    old_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    (backup / 'previous-commit.txt').write_text(old_head + '\n')
    old_images = {}
    for service, container in [('backend', backend), ('frontend', frontend)]:
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
    settings = env(preview)
    agent = {key: settings[key] for key in ['OPENAI_API_KEY', 'OPENAI_MODEL', 'GOONG_REST_API_KEY', 'AGENT_ENABLED', 'AGENT_DAILY_MODEL_CALL_LIMIT', 'AGENT_MAX_ROUNDS'] if key in settings}
    if not agent.get('OPENAI_API_KEY') or not agent.get('GOONG_REST_API_KEY'):
        raise RuntimeError('Authorized preview credentials are missing')
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
    run(['docker', 'exec', '--user', '0', backend['Id'], 'chown', '-R', '10001:10001', '/runtime/agent-pois'])
    run(['git', 'fetch', 'origin'], cwd=ROOT)
    run(['git', 'switch', 'main'], cwd=ROOT)
    run(['git', 'merge', '--ff-only', 'origin/main'], cwd=ROOT)
    compose = ['docker', 'compose', '-p', 'urbandynamics', '--env-file', '.env', '--env-file', '.env.production.local', '-f', 'compose.yaml', '-f', 'compose.production-agent.yaml']
    # Validate and build before recreating any live service. Never restart PostGIS.
    run(compose + ['config', '--quiet'], cwd=ROOT)
    run(compose + ['build', 'backend', 'frontend'], cwd=ROOT)
    run(compose + ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', 'backend', 'planning-worker', 'traffic-prediction-worker', 'frontend'], cwd=ROOT)
    (backup / 'deployed-commit.txt').write_text(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True))
    print(json.dumps({'status': 'deployed', 'port': 51873, 'backup': str(backup)}))


if __name__ == '__main__':
    main()
