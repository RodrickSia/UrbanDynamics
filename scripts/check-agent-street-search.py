"""Live source + real model regression for the user's named-alley request/scope."""
import json
from pathlib import Path
from uuid import uuid4

import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results/general-agent/street-search-result.json'
BASE='http://127.0.0.1:8192'


def api(path,body):
    response=requests.post(BASE+path,json=body,timeout=180)
    if not response.ok:raise RuntimeError(f'{response.status_code}: {response.text[:500]}')
    return response.json()


def main():
    # Deliberately keep an unrelated visible Thu Duc viewport. The request must
    # locate Go Vap from source geometry, never reuse this viewport silently.
    viewport=json.loads((ROOT/'test-results/general-agent/live-result.json').read_text(encoding='utf-8'))['viewport']
    session=api('/api/v1/agent/sessions',{});sid=session['session_id']
    evidence={'session_id':sid,'unrelated_viewport':viewport,'tools':[],'turns':[]}
    def save():
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    def tool(name,args):
        value=api(f'/api/v1/agent/sessions/{sid}/tools/{name}',{'arguments':args,'workspace':{'viewport':viewport}})
        evidence['tools'].append({'name':name,'response':value});save()
        return value['tool_result']
    street=tool('area_select',{'source':'street','query':'Hẻm 114 đường Trần Quốc Tuấn','bbox':None,'match_index':None})
    assert street['street_name']=='Hẻm 114 Trần Quốc Tuấn'
    assert 106.68<street['bbox'][0]<street['bbox'][2]<106.70
    candidates=tool('candidate_search',{'minimum_area_m2':40,'maximum_area_m2':1000,'land_use_codes':[],'bbox':None,'limit':6})
    assert candidates['candidates'],'No parcel source coverage around the alley'
    assert all('distance_to_requested_street_m' in f['properties'] for f in candidates['candidates'])
    # Use a clean model conversation, not the direct-tool session above.
    model=api('/api/v1/agent/sessions',{})
    evidence['model_session_id']=model['session_id'];save()
    prompts=[
        'tìm khu vực để xây căn nhà 4 tầng ở hẻm 114 đường trần quốc tuấn quận gò vấp',
        'tìm những khu vực gần bệnh viện, công viên để xây nhà',
    ]
    for i,prompt in enumerate(prompts):
        value=api('/api/v1/agent/chat',{'session_id':model['session_id'],'request_id':str(uuid4()),
            'workspace':{'viewport':viewport},'message':prompt,'allow_native':False})
        evidence['turns'].append({'prompt':prompt,'response':value});save()
        successful={t['tool'] for t in value['trace'] if t['status']=='succeeded'}
        if i==0:
            assert {'area_select','candidate_search'}<=successful,value['trace']
            assert value['analysis_area']['street_name']=='Hẻm 114 Trần Quốc Tuấn'
            assert 'simulation_start' not in successful and 'candidate_study_start' not in successful
        else:
            assert not {'candidate_search','amenity_site_search'}&successful,value['trace']
            assert '?' in value['answer'],'Agent must ask a geographic scope question, not silently reuse old results'
    print(json.dumps({'passed':True,'street':street['street_name'],'bbox':street['bbox'],
        'source_parcels':len(candidates['candidates']),
        'turns':[{'prompt':t['prompt'],'answer':t['response']['answer'],'trace':t['response']['trace']} for t in evidence['turns']]},ensure_ascii=False))


if __name__=='__main__':main()
