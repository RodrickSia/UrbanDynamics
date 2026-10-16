import json
from copy import deepcopy
from uuid import uuid4
import pytest

from test_zoning import client, plan, command
from test_development import building, parcel_source
from app.services.agent import store, service, tools
from app.services.agent import development_tools as dt
from app.services.zoning import baseline
from app.services.simulation.planning.jobs import process_one


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setenv('AGENT_ENABLED','1')
    monkeypatch.setenv('AGENT_SQLITE_PATH',str(tmp_path/'agent.sqlite'))
    monkeypatch.setenv('PLANNING_SQLITE_PATH',str(tmp_path/'planning.sqlite'))
    monkeypatch.setenv('SIMULATION_WORK_DIR',str(tmp_path/'solvers'))
    monkeypatch.setenv('PLANNING_SYSTEM_SNAPSHOT_DIR',str(tmp_path/'snapshots'))
    monkeypatch.setenv('PLANNING_COUNTING_REFERENCE_DIR',str(tmp_path/'counting'))
    monkeypatch.setattr(baseline,'buildings',lambda *a:None)


def bound(plan):
    s=store.create()
    dt.bind_workspace(s,{'plan_id':plan['id'],'revision':plan['revision'],'scenario_id':plan['scenarios'][1]['id'],
                         'parcel_id':'3885881','building_id':plan['scenarios'][1]['buildings'][0]['id']})
    return s


def test_current_building_edit_preserves_geometry_and_floor_program(client,plan,parcel_source):
    plan=command(client,plan,'save_building',building(floor_overrides=[{'floor':1,'floor_height':4,'space_use_id':'commercial'}]))
    s=bound(plan)
    previous=deepcopy(plan['scenarios'][1]['buildings'][0])
    out=tools.execute('building_save',{'building_id':previous['id'],'patch_json':json.dumps({'floors':4})},s,False)
    saved=out['saved_building']
    assert json.loads(json.dumps(saved['geometry']))==previous['geometry']
    assert saved['floor_overrides']==previous['floor_overrides']
    assert saved['floors']==4 and s['workspace']['revision']==plan['revision']+1
    assert dt.workspace_view(s)['building_count']==1


def test_stale_dirty_and_locked_plan_are_rejected(client,plan,parcel_source):
    plan=command(client,plan,'save_building',building())
    s=bound(plan)
    s['workspace']['dirty']=True
    with pytest.raises(ValueError,match='unsaved'):
        tools.execute('building_save',{'building_id':None,'patch_json':'{"floors":3}'},s,False)
    s['workspace']['dirty']=False
    newer=command(client,plan,'save_building',{**building(),'id':plan['scenarios'][1]['buildings'][0]['id'],'floors':3})
    with pytest.raises(ValueError,match='changed'):
        dt.current(s,True)
    s=bound(newer)
    s['workspace']['scenario_id']=newer['scenarios'][0]['id']
    with pytest.raises(ValueError,match='read-only'):
        dt.current(s,True)


def test_duplicate_then_edit_uses_new_ids_and_preserves_original(client,plan,parcel_source):
    plan=command(client,plan,'save_building',building())
    s=bound(plan)
    old=plan['scenarios'][1]['buildings'][0]
    view=tools.execute('scenario_duplicate',{'name':'Six-floor alternative'},s,False)
    new=view['buildings'][0]
    assert new['id']!=old['id']
    tools.execute('building_save',{'building_id':new['id'],'patch_json':'{"floors":6}'},s,False)
    document=dt.current(s)[0]
    assert document['scenarios'][1]['buildings'][0]['floors']==2
    assert document['scenarios'][-1]['buildings'][0]['floors']==6


def test_prepare_start_results_and_stale_revision(client,plan,parcel_source):
    plan=command(client,plan,'save_building',building())
    s=bound(plan)
    prepared=tools.execute('simulation_prepare',{'scope':'scenario','settings_json':'{}'},s,False)
    args={'prepared_id':prepared['prepared_id'],'mode':'screening'}
    first=tools.execute('simulation_start',args,s,False)
    assert tools.execute('simulation_start',args,s,False)['job']['id']==first['job']['id']
    assert process_one()['status']=='succeeded'
    view=tools.execute('simulation_results',{'job_ids':[first['job']['id']]},s,False)
    assert view['jobs'][0]['results']['options']
    assert not view['jobs'][0]['stale_plan_revision']
    tools.execute('building_save',{'building_id':None,'patch_json':'{"floors":5}'},s,False)
    assert tools.execute('simulation_results',{'job_ids':[first['job']['id']]},s,False)['jobs'][0]['stale_plan_revision']
    with pytest.raises(ValueError,match='stale'):
        tools.execute('simulation_start',args,s,False)
    with pytest.raises(ValueError,match='session'):
        tools.execute('simulation_results',{'job_ids':[str(uuid4())]},s,False)


def test_native_needs_checkbox_and_no_invented_geometry(client,plan,parcel_source):
    plan=command(client,plan,'save_building',building())
    s=bound(plan)
    prepared=tools.execute('simulation_prepare',{'scope':'scenario','settings_json':'{}'},s,False)
    with pytest.raises(ValueError,match='Enable detailed'):
        tools.execute('simulation_start',{'prepared_id':prepared['prepared_id'],'mode':'native'},s,False)
    s['workspace'].pop('building_id')
    with pytest.raises(ValueError,match='Draw a footprint'):
        tools.execute('building_save',{'building_id':None,'patch_json':'{"floors":3}'},s,False)


def test_paired_verification_preserves_program_and_reuses_jobs(client,plan,parcel_source):
    plan=command(client,plan,'save_building',building())
    s=bound(plan)
    prepared=tools.execute('simulation_prepare',{'scope':'scenario','settings_json':'{}'},s,False)
    args={'prepared_id':prepared['prepared_id'],'goal':'power','mode':'screening'}
    pair=tools.execute('simulation_verify',args,s,False)
    assert len(pair['jobs'])==2
    assert tools.execute('simulation_verify',args,s,False)['reused']
    assert process_one()['status']=='succeeded'
    assert process_one()['status']=='succeeded'
    result=tools.execute('simulation_results',{'job_ids':[j['job_id'] for j in pair['jobs']]},s,False)
    assert result['paired_input_audit']['same_building_program']
    assert result['paired_input_audit']['same_inputs_except_design_controls']


def test_chat_model_tool_loop_and_request_replay(client,plan,parcel_source,monkeypatch):
    plan=command(client,plan,'save_building',building())
    s=bound(plan)
    monkeypatch.setattr(service,'configured',lambda:True)
    calls=[]
    def model(inputs):
        calls.append(inputs)
        if len(calls)==1:
            return {'output':[{'type':'function_call','name':'workspace_read','call_id':'one','arguments':'{}'}]}
        return {'output':[{'type':'message','content':[{'type':'output_text','text':'The selected building has 2 floors. Capacity is unknown.'}]}]}
    monkeypatch.setattr(service,'model_response',model)
    body={'session_id':s['id'],'request_id':str(uuid4()),'message':'Explain my selected building','workspace':s['workspace']}
    response=client.post('/api/v1/agent/chat',json=body)
    assert response.status_code==200,response.text
    assert response.json()['trace'][0]['tool']=='workspace_read'
    assert client.post('/api/v1/agent/chat',json=body).json()['answer']==response.json()['answer']
    assert len(calls)==2


def test_api_requires_enabled_and_rejects_arbitrary_fields(client,monkeypatch):
    monkeypatch.setenv('AGENT_ENABLED','0')
    assert client.post('/api/v1/agent/sessions',json={}).status_code==404
    monkeypatch.setenv('AGENT_ENABLED','1')
    s=client.post('/api/v1/agent/sessions',json={}).json()
    assert client.post('/api/v1/agent/sessions/'+s['session_id']+'/tools/workspace_read',json={'workspace':{'shell':'whoami'}}).status_code==422


def test_authorized_native_uses_same_development_run_route(client,plan,parcel_source,monkeypatch):
    plan=command(client,plan,'save_building',building())
    s=bound(plan)
    prepared=tools.execute('simulation_prepare',{'scope':'scenario','settings_json':'{"traffic_radius_m":1000,"rainfall_mm":80}'},s,False)
    seen=[]
    def run(identifier,body):
        seen.append(body)
        return {'job':{'id':str(uuid4()),'status':'queued'},'study':{'id':'saved-native'}}
    monkeypatch.setattr(dt.zoning,'simulation_run',run)
    tools.execute('simulation_start',{'prepared_id':prepared['prepared_id'],'mode':'native'},s,True)
    assert seen[0].mode=='native' and seen[0].traffic_radius_m==1000 and seen[0].rainfall_mm==80
    assert seen[0].revision==plan['revision']
