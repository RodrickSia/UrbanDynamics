"""Run agent regressions against a disposable PostGIS, never the team database."""
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
HOST='nguyenmv@192.168.20.156'
TARGET='/GuestShare_NAS/WorkingSpace/Personal/nguyenmv/MLAI/UrbanDynamics/development-preview/query-tests'
OUT=ROOT/'test-results/query-upgrade'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    archive=OUT/'source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for parent in ('backend','etl/src'):
            for file in (ROOT/parent).rglob('*'):
                if not file.is_file() or any(x in file.parts for x in ('__pycache__','.venv','.runtime','node_modules')) or file.name.startswith('.env'):continue
                tar.add(file,arcname=str(file.relative_to(ROOT)),recursive=False)
        catalog=ROOT/'frontend/src/features/zoning/zoningCatalog.json'
        tar.add(catalog,arcname=str(catalog.relative_to(ROOT)),recursive=False)
    subprocess.run(['ssh','-o','BatchMode=yes',HOST,'mkdir -p '+TARGET],check=True,capture_output=True,timeout=15)
    subprocess.run(['scp','-q',str(archive),HOST+':'+TARGET+'/source.tar.gz'],check=True,capture_output=True,timeout=90)
    code=r'''
import json,os,secrets,subprocess,tarfile,time
from pathlib import Path
target=Path(TARGET)
with tarfile.open(target/'source.tar.gz') as tar:
 for member in tar.getmembers():
  if os.path.commonpath([str((target/member.name).resolve()),str(target.resolve())])!=str(target.resolve()) or member.issym() or member.islnk():raise ValueError('Invalid archive')
 tar.extractall(target)
def run(args,**kwargs):return subprocess.run(args,capture_output=True,text=True,check=True,**kwargs)
suffix=secrets.token_hex(4);network='agent-query-test-'+suffix;database='agent-query-test-db-'+suffix
password=secrets.token_hex(12)
db_image=json.loads(run(['docker','inspect','urbandynamics-postgis-1']).stdout)[0]['Config']['Image']
image=json.loads(run(['docker','inspect','urbandynamics-development-preview-backend-1']).stdout)[0]['Config']['Image']
created=False
try:
 run(['docker','network','create',network]);created=True
 run(['docker','run','-d','--name',database,'--network',network,'--network-alias','agent-query-test-db','--memory','1g','--shm-size','128m','--tmpfs','/var/lib/postgresql/data','-e','POSTGRES_USER=agent_test','-e','POSTGRES_PASSWORD='+password,'-e','POSTGRES_DB=agent_tests',db_image])
 for attempt in range(30):
  ready=subprocess.run(['docker','exec',database,'pg_isready','-U','agent_test','-d','agent_tests'],capture_output=True)
  if ready.returncode==0:break
  time.sleep(1)
 else:raise RuntimeError('Disposable PostGIS failed to start')
 url='postgresql://agent_test:'+password+'@agent-query-test-db:5432/agent_tests'
 command=['docker','run','--rm','--user','0:0','--network',network,'-v',str(target)+':/workspace:ro','-w','/workspace','-e','PYTHONPATH=/workspace/backend:/workspace/etl','-e','AGENT_TEST_DATABASE_URL='+url,'-e','TEST_DATABASE_URL='+url,'--entrypoint','/bin/sh',image,'-c',
 'uv pip install --python /app/.venv/bin/python pytest httpx >/tmp/test-install.log 2>&1 && /app/.venv/bin/python -m pytest backend/tests/test_agent_dataset_query.py backend/tests/test_general_agent.py backend/tests/test_development_agent.py backend/tests/test_goong_places.py backend/tests/test_query_postgis.py backend/tests/test_agent_accessibility.py backend/tests/test_agent_scope.py backend/tests/test_plan_projection.py -q --tb=short -p no:cacheprovider']
 result=subprocess.run(command,capture_output=True,text=True,timeout=180)
 print(json.dumps({'exit_code':result.returncode,'output':(result.stdout+result.stderr).replace(password,'[TEST_PASSWORD]').replace(url,'[TEST_DATABASE]')}))
finally:
 subprocess.run(['docker','rm','-f',database],capture_output=True)
 if created:subprocess.run(['docker','network','rm',network],capture_output=True)
'''.replace('TARGET',repr(TARGET))
    result=subprocess.run(['ssh','-o','BatchMode=yes',HOST,'python3 -'],input=code,text=True,capture_output=True,timeout=240)
    if result.returncode:raise RuntimeError('Remote test orchestration failed: '+result.stderr[-1000:])
    value=json.loads(result.stdout)
    (OUT/'postgis-tests.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    print(value['output'][-7000:])
    if value['exit_code']:raise SystemExit(value['exit_code'])


if __name__=='__main__':main()
