"""Real warehouse + shared solver verification of urban tools without an open plan."""
import json
import time
from pathlib import Path
from uuid import uuid4
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results'/'general-agent'
BASE='http://127.0.0.1:8192'
EVIDENCE={}

def api(path,body=None,timeout=180):
    r=requests.get(BASE+path,timeout=timeout) if body is None else requests.post(BASE+path,json=body,timeout=timeout)
    j=r.json()
    if not r.ok:raise RuntimeError(f'{path} HTTP {r.status_code}: {str(j)[:350]}')
    return j

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source=api('/api/v1/zoning/plans/36918473-9a5d-4027-bd69-f10b61367e43')
    coords=source['study_area']['coordinates'][0]
    bbox=[min(p[0] for p in coords),min(p[1] for p in coords),max(p[0] for p in coords),max(p[1] for p in coords)]
    session=api('/api/v1/agent/sessions',{})
    EVIDENCE.update(session_id=session['session_id'],viewport=bbox)
    def tool(name,args):
        response=api(f'/api/v1/agent/sessions/{session["session_id"]}/tools/{name}',{'arguments':args,'workspace':{'viewport':bbox}})
        EVIDENCE.setdefault('tools',[]).append({'name':name,'response':response})
        return response['tool_result']
    tool('platform_overview',{})
    tool('area_select',{'source':'viewport','query':None,'parcel_id':None,'bbox':None,'match_index':None})
    area=tool('area_analyze',{'population_year':2026})
    assert area['population']['year']==2026
    search=tool('candidate_search',{'minimum_area_m2':2000,'maximum_area_m2':100000,'land_use_codes':[],'bbox':None,'limit':6})
    ids=[str(f['id']) for f in search['candidates']]
    assert len(ids)>=2
    comparison=tool('candidate_compare',{'parcel_ids':ids[:2],'population_year':2026,
        'criteria_json':json.dumps([{'metric':'population_density','direction':'maximize','weight':1},
                                   {'metric':'road_distance_m','direction':'minimize','weight':1},
                                   {'metric':'area_m2','direction':'maximize','weight':.5}])})
    program={'use':'school','floors':3,'floor_area_m2':600,'staff':10,'daily_users':100,'service_capacity':100,'setback_m':1}
    prepared=None
    for i in range(len(ids)-1):
        try:
            prepared=tool('candidate_study_prepare',{'parcel_ids':ids[i:i+2],'program_json':json.dumps(program),'rainfall_mm':60})
            break
        except RuntimeError as e:
            EVIDENCE.setdefault('fit_rejections',[]).append(str(e))
    assert prepared,'No two sites passed the unchanged-program preliminary fit test'
    job=tool('candidate_study_start',{'study_id':prepared['study_id'],'mode':'screening'})['job']
    assert tool('candidate_study_start',{'study_id':prepared['study_id'],'mode':'screening'})['job']['id']==job['id']
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        status=api('/api/v1/planning/jobs/'+job['id'])
        if status['status'] not in ('queued','running'):break
        time.sleep(2)
    assert status['status']=='succeeded',status
    result=tool('urban_results',{'job_ids':[job['id']]})
    assert len(result['jobs'][0]['results']['options'])==2
    report=tool('urban_report',{})
    assert 'markdown' in report
    (OUT/'evidence-report.md').write_text(report['markdown'],encoding='utf-8')
    EVIDENCE['checks']={'no_open_plan_required':True,'source_parcels':ids,'area_population':area['population'],
        'ranking_status':comparison['ranking_status'],'school_comparison_succeeded':True,'job_id':job['id'],'report_export':True}
    # One real model turn must use the general workflow rather than demand a plan.
    reply=api('/api/v1/agent/chat',{'session_id':session['session_id'],'workspace':{'viewport':bbox},'request_id':str(uuid4()),
        'message':'Không cần mở plan. Hãy đọc urban_report và urban_results cho job '+job['id']+', rồi giải thích so sánh các khu đất cho cùng trường học. Nêu nguồn, tiêu chí còn thiếu và không coi đất là trống. Trả lời ngắn bằng tiếng Việt.'},timeout=240)
    EVIDENCE['live_model']=reply
    assert any(t['tool']=='urban_results' and t['status']=='succeeded' for t in reply['trace']),reply['trace']
    EVIDENCE['checks']['live_model_tools']=reply['trace']
    print(json.dumps(EVIDENCE['checks'],ensure_ascii=True))

if __name__=='__main__':
    try:main()
    finally:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'live-result.json').write_text(json.dumps(EVIDENCE,ensure_ascii=False,indent=2),encoding='utf-8')
