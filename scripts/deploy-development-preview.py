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
    if old_env.is_file():
        for line in old_env.read_text().splitlines():
            if line.startswith('VITE_GOONG_MAPTILES_KEY='):
                settings['VITE_GOONG_MAPTILES_KEY']=line.split('=',1)[1].strip('"\'')
    code=r'''
import json,subprocess,tarfile,os
from pathlib import Path
target=Path(TARGET)
assert target.name=='development-preview' and target.resolve()==Path(TARGET)
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
file.write_text(''.join(k+'='+v+'\n' for k,v in settings.items()))
file.chmod(0o600)
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
