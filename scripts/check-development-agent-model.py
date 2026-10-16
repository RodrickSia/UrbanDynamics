"""One bounded real-model write/run turn on the integration test plan only."""
import json
import time
from pathlib import Path
from uuid import uuid4
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results'/'development-agent'
BASE='http://127.0.0.1:8192'

def main():
    previous=json.loads((OUT/'live-result.json').read_text(encoding='utf-8'))
    live=previous['live_model']
    binding=live['workspace']
    assert binding['plan_id']==previous['test_plan_id']
    started=time.monotonic()
    response=requests.post(BASE+'/api/v1/agent/chat',json={'session_id':live['session_id'],'workspace':binding,
        'request_id':str(uuid4()),'allow_native':False,
        'message':'Duplicate the current scenario as "Luna verified alternative". In the duplicate, change the only building to 5 floors, preserving footprint, use and all unspecified fields. Then prepare and start a quick estimate for the whole scenario using defaults. Do not change the original scenario. Include saved revision and job status.'},timeout=240)
    value=response.json()
    assert response.ok,(response.status_code,value)
    record={'elapsed_seconds':round(time.monotonic()-started,2),'response':value}
    (OUT/'model-write-result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    assert any(t['tool']=='building_save' and t['status']=='succeeded' for t in value['trace']),value['trace']
    assert any(t['tool']=='simulation_start' and t['status']=='succeeded' for t in value['trace']),value['trace']
    plan=requests.get(BASE+'/api/v1/zoning/plans/'+binding['plan_id'],timeout=30).json()
    original=next(s for s in plan['scenarios'] if s['id']==binding['scenario_id'])
    alternative=next(s for s in plan['scenarios'] if s['id']==value['workspace']['scenario_id'])
    assert original['buildings'][0]['floors']==4
    assert alternative['buildings'][0]['floors']==5
    assert alternative['buildings'][0]['geometry']==original['buildings'][0]['geometry']
    print(json.dumps({'passed':True,'elapsed_seconds':record['elapsed_seconds'],'trace':value['trace'],'original_floors':4,'alternative_floors':5}))

if __name__=='__main__':
    main()
