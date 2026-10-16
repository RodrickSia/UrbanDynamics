"""Deploy ONLY the separate development-preview directory and Compose project."""
import json
import argparse
import os
import re
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=ROOT.parent/'UrbanDynamics'
OUT=ROOT/'test-results'/'development-context'
HOST='nguyenmv@192.168.20.156'
TARGET='/GuestShare_NAS/WorkingSpace/Personal/nguyenmv/MLAI/UrbanDynamics/development-preview'


def ssh(code):
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',HOST,'python3 -'],
                          input=code.encode(),capture_output=True,timeout=90)
    if result.returncode:
        reason=result.stderr.decode(errors='replace').splitlines()[-1] if result.stderr else 'unknown'
        reason=re.sub(r'sk-[A-Za-z0-9_-]+','[REDACTED]',reason)
        raise RuntimeError('Remote preview step failed: '+reason[:250])
    return result.stdout.decode()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--frontend-only',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    previous=OUT/'server-deployment.json'
    if previous.is_file():
        pid=int(json.loads(previous.read_text())['pid'])
        ssh('import os,signal\nfrom pathlib import Path\npid='+str(pid)+'\np=Path("/proc")/str(pid)/"cmdline"\nif p.is_file() and b"compose.development-preview.yaml" in p.read_bytes() and os.getpgid(pid)==pid:\n os.killpg(pid,signal.SIGTERM)\n')
    ssh('from pathlib import Path\np=Path('+repr(TARGET)+')\nassert p.name=="development-preview"\np.mkdir(parents=True,exist_ok=True)')
    files=set(subprocess.check_output(['git','ls-files','backend','frontend','etl/src','scripts','compose.development-preview.yaml','compose.development-server.yaml'],cwd=ROOT,text=True).splitlines())
    files.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines())
    archive=OUT/'source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for relative in sorted(files):
            if not relative.startswith(('backend/','frontend/','etl/src/','scripts/','compose.development')):
                continue
            if '/node_modules/' in relative or Path(relative).name.startswith('.env'):
                continue
            tar.add(ROOT/relative,arcname=relative,recursive=False)
    datasets=OUT/'datasets.tar.gz'
    source=ORIGINAL/'.runtime'/'planning-system'/'snapshots'
    with tarfile.open(datasets,'w:gz') as tar:
        for path in source.glob('*.json'):
            tar.add(path,arcname='snapshots/'+path.name)
        for path in (source/'counting').glob('*'):
            if path.is_file() and (path.suffix=='.json' or path.name=='default-reference.txt'):
                tar.add(path,arcname='counting/'+path.name)
    for file in (archive,datasets):
        subprocess.run(['scp','-q','-o','BatchMode=yes',str(file),HOST+':'+TARGET+'/'+file.name],check=True,capture_output=True,timeout=180)
    settings={}
    old_env=ROOT.parent/'UrbanDynamics-agent-web'/'.env.agent.local'
    # Dedicated ignored preview override wins over the previous shared map key.
    for map_env in (old_env, ROOT/'.env.development-goong.local'):
        if map_env.is_file():
            for line in map_env.read_text().splitlines():
                if line.startswith(('VITE_GOONG_MAPTILES_KEY=','GOONG_REST_API_KEY=')):
                    name,value=line.split('=',1)
                    settings[name]=value.strip('"\'')
    code=r'''
import json,subprocess,tarfile,os
from pathlib import Path
target=Path(TARGET)
assert target.name=='development-preview' and target.resolve()==Path(TARGET)
if not FRONTEND_ONLY:
 check="import sqlite3; from pathlib import Path; p=Path('/runtime/studies.sqlite'); print(sqlite3.connect(p).execute(\"SELECT count(*) FROM planning_jobs WHERE status IN ('queued','running')\").fetchone()[0] if p.exists() else 0)"
 active=subprocess.run(['docker','exec','urbandynamics-development-preview-backend-1','python','-c',check],capture_output=True,text=True)
 if active.returncode==0 and int(active.stdout.strip())>0:
  raise RuntimeError('Development preview has active jobs; collect their results before redeploying backend/worker')
for archive,dest in [('source.tar.gz',target),('datasets.tar.gz',target/'datasets')]:
 dest.mkdir(parents=True,exist_ok=True)
 with tarfile.open(target/archive) as tar:
  for member in tar.getmembers():
   if os.path.commonpath([str((dest/member.name).resolve()),str(dest.resolve())])!=str(dest.resolve()) or member.issym() or member.islnk():
    raise ValueError('Invalid archive member')
  tar.extractall(dest)
backend=json.loads(subprocess.check_output(['docker','inspect','urbandynamics-backend-1'],text=True))[0]
env=dict(v.split('=',1) for v in backend['Config']['Env'] if '=' in v)
settings=SETTINGS
for key in ['WAREHOUSE_PORT','WAREHOUSE_DATABASE','WAREHOUSE_USER','WAREHOUSE_PASSWORD']:
 settings[key]=env.get(key,'')
settings.update(WAREHOUSE_HOST='team-postgis',DEV_WEB_PORT='51875',DEV_API_PORT='8022',DEV_BACKEND_BASE_IMAGE='urbandynamics-backend:latest',
 DEV_SNAPSHOT_DIR=str(target/'datasets'/'snapshots'),DEV_COUNTING_DIR=str(target/'datasets'/'counting'),
 DEV_DATA_DIR=next(m['Source'] for m in backend['Mounts'] if m['Destination']=='/data'))
network='urbandynamics-development-preview-data'
if subprocess.run(['docker','network','inspect',network],capture_output=True).returncode:
 subprocess.run(['docker','network','create',network],check=True,stdout=subprocess.DEVNULL)
warehouse=json.loads(subprocess.check_output(['docker','inspect','urbandynamics-postgis-1'],text=True))[0]
if network not in warehouse['NetworkSettings']['Networks']:
 subprocess.run(['docker','network','connect','--alias','team-postgis',network,'urbandynamics-postgis-1'],check=True,stdout=subprocess.DEVNULL)
file=target/'.env.development.local'
rest_key=settings.pop('GOONG_REST_API_KEY','')
file.write_text(''.join(k+'='+v+'\n' for k,v in settings.items()))
file.chmod(0o600)
if not FRONTEND_ONLY:
 # Reuse the explicitly authorized existing model configuration, server-to-server only.
 # This file is backend-only; workers and frontend never receive the model credential.
 configured=subprocess.run(['docker','inspect','urbandynamics-agent-preview-backend-1'],capture_output=True,text=True)
 if configured.returncode==0:
  original=json.loads(configured.stdout)[0]
  model_env=dict(v.split('=',1) for v in original['Config']['Env'] if '=' in v)
  if model_env.get('OPENAI_API_KEY'):
   agent={k:model_env[k] for k in ('OPENAI_API_KEY','OPENAI_MODEL') if k in model_env}
   agent.update(AGENT_ENABLED='1',AGENT_DAILY_MODEL_CALL_LIMIT='200',AGENT_MAX_ROUNDS='8')
   agent_file=target/'.env.development-agent.local'
   agent_file.write_text(''.join(k+'='+v+'\n' for k,v in agent.items()))
   agent_file.chmod(0o600)
 if rest_key:
  agent_file=target/'.env.development-agent.local'
  existing=agent_file.read_text().splitlines() if agent_file.exists() else []
  existing=[line for line in existing if not line.startswith('GOONG_REST_API_KEY=')]
  agent_file.write_text('\n'.join(existing)+'\nGOONG_REST_API_KEY='+rest_key+'\n')
  agent_file.chmod(0o600)
log=open(target/'preview-deploy.log','ab',buffering=0)
command=['docker','compose','--env-file','.env.development.local','-f','compose.development-preview.yaml','-f','compose.development-server.yaml','up','--build','-d']
if FRONTEND_ONLY:
 command+=['--no-deps','frontend']
process=subprocess.Popen(command,cwd=target,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
print(json.dumps({'pid':process.pid,'web_port':51875,'api_port':8022,'directory':str(target)}))
'''.replace('TARGET',repr(TARGET)).replace('SETTINGS',repr(settings)).replace('FRONTEND_ONLY',repr(args.frontend_only))
    result=json.loads(ssh(code))
    (OUT/'server-deployment.json').write_text(json.dumps(result,indent=2))
    print('Separate Development preview build started on server 156, loopback port 51875.')


if __name__=='__main__':
    main()
