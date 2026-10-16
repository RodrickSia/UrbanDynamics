"""Exercise the isolated preview using a disposable test plan, never edit the user's plan."""
import json
import time
from pathlib import Path
from uuid import uuid4
import requests

BASE='http://127.0.0.1:8192'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results'/'development-agent'
OUT.mkdir(parents=True,exist_ok=True)
evidence={}

def api(path,body=None):
    response=requests.get(BASE+path,timeout=30) if body is None else requests.post(BASE+path,json=body,timeout=180)
    value=response.json()
    if not response.ok:
        raise RuntimeError(f'{path}: HTTP {response.status_code}: '+str(value)[:400])
    return value

def main():
    config=api('/api/v1/agent/config')
    assert config['enabled'] and config['model_configured'],config
    source=api('/api/v1/zoning/plans/36918473-9a5d-4027-bd69-f10b61367e43')
    plan=api('/api/v1/zoning/plans',{'name':'Agent integration check · Development','description':'Isolated assistant test plan; does not modify the guided user plan.','study_area':source['study_area']})
    building=next(b for s in source['scenarios'] for b in s.get('buildings',[]))
    payload={k:building[k] for k in ('geometry','parcel_id','floors','floor_height','space_use_id','counts_gfa','counts_far','floor_overrides') if k in building}
    plan=api(f'/api/v1/zoning/plans/{plan["id"]}/commands',{'revision':plan['revision'],'scenario_id':plan['scenarios'][1]['id'],'action':'save_building','payload':{**payload,'name':'Agent test building'}})
    session=api('/api/v1/agent/sessions',{})
    binding={'plan_id':plan['id'],'revision':plan['revision'],'scenario_id':plan['scenarios'][1]['id'],
             'parcel_id':building['parcel_id'],'building_id':plan['scenarios'][1]['buildings'][0]['id'],'dirty':False}
    evidence.update(config=config,source_revision=source['revision'],test_plan_id=plan['id'],session_id=session['session_id'])
    def tool(name,args):
        nonlocal session,binding
        result=api(f'/api/v1/agent/sessions/{session["session_id"]}/tools/{name}',{'workspace':binding,'arguments':args})
        evidence.setdefault('tools',[]).append({'name':name,'response':result})
        session=result
        if result.get('workspace_changed'):
            binding=result['workspace']
        return result['tool_result']
    tool('workspace_read',{})
    tool('source_catalog',{})
    tool('site_context',{'parcel_id':building['parcel_id']})
    tool('site_search',{'minimum_area_m2':500,'maximum_area_m2':100000,'land_use_codes':[],'limit':3,'bbox':None})
    tool('scenario_duplicate',{'name':'Agent alternative · 4 floors'})
    view=tool('workspace_read',{})
    target=view['buildings'][0]
    tool('building_save',{'building_id':target['id'],'patch_json':json.dumps({'floors':4})})
    prepared=tool('simulation_prepare',{'scope':'scenario','settings_json':'{}'})
    job=tool('simulation_start',{'prepared_id':prepared['prepared_id'],'mode':'screening'})['job']
    repeat=tool('simulation_start',{'prepared_id':prepared['prepared_id'],'mode':'screening'})
    assert repeat['job']['id']==job['id']
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=api('/api/v1/planning/jobs/'+job['id'])
        if state['status'] not in ('queued','running'):
            break
        time.sleep(2)
    assert state['status']=='succeeded',state
    result=tool('simulation_results',{'job_ids':[job['id']]})
    assert result['jobs'][0]['results']['options']
    tool('simulation_latest',{})
    live=api('/api/v1/agent/chat',{'session_id':session['session_id'],'workspace':binding,'request_id':str(uuid4()),
        'message':'Use workspace_read and simulation_results to explain my current building and the completed quick result. State what baseline/capacity is missing. Do not edit or run another job.'})
    evidence['live_model']=live
    assert any(t['status']=='succeeded' for t in live['trace']),live
    user_after=api('/api/v1/zoning/plans/'+source['id'])
    assert user_after['revision']==source['revision'],'User plan unexpectedly changed'
    evidence['checks']={'model_connected':True,'tools_succeeded':len(evidence['tools']),'screening_succeeded':True,
                        'duplicate_job_reused':True,'user_plan_untouched':True,'live_model_tools':live['trace']}
    (OUT/'live-result.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence['checks'],ensure_ascii=True))

if __name__=='__main__':
    try:
        main()
    except Exception as error:
        evidence['error']=str(error)
        (OUT/'live-result.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(str(error).encode('ascii',errors='replace').decode())
        raise SystemExit(1)
