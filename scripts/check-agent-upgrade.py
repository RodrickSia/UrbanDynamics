"""Semantic acceptance cases on real preview data + real model (three turns)."""
import json
from pathlib import Path
from uuid import uuid4
import requests
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results/query-upgrade/live-cases.json'
BASE='http://127.0.0.1:8192'
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'etl')]
from app.services.agent.dataset_query import evaluate
from app.services.agent.language import hint


def api(path,body=None):
    response=requests.get(BASE+path,timeout=90) if body is None else requests.post(BASE+path,json=body,timeout=180)
    if not response.ok:raise RuntimeError(f'{response.status_code}: {response.text[:800]}')
    return response.json()


def main():
    previous=json.loads((ROOT/'test-results/general-agent/structured-query-result.json').read_text(encoding='utf-8'))
    viewport=previous['viewport']
    session=api('/api/v1/agent/sessions',{})['session_id']
    evidence={'session_id':session,'tools':[],'turns':[]}
    def save():
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    def tool(name,args,workspace=None):
        value=api(f'/api/v1/agent/sessions/{session}/tools/{name}',{'arguments':args,'workspace':workspace or {'viewport':viewport}})
        evidence['tools'].append({'name':name,'response':value});save()
        return value['tool_result']
    tool('area_select',{'source':'viewport'})
    result=tool('dataset_query',{'query_json':json.dumps({'layer':'parcels','joins':[
        {'layer':'land_price','alias':'price','radius_m':300,'where':{'field':'residential_vnd_m2','op':'between','value':{'min':20,'max':40,'unit':'million_vnd_per_m2'}}}],
        'order_by':[{'field':'area_m2','direction':'asc'}],'limit':3,'aggregates':[{'op':'count'}]})})
    assert result['query_engine']=='postgis' and result['returned']==3
    assert result['aggregates'][0]['metrics'][0]['value']==result['matched_count']>3
    assert all(20000000<=r['price.residential_vnd_m2']<=40000000 and r['price.distance_m']<=300 for r in result['rows'])
    assert all(s['fetch_limit'] is None for s in result['sources'])
    refined=tool('dataset_query_refine',{'query_id':result['id'],'patch_json':json.dumps({'where':{'field':'area_m2','op':'between','value':[40,1000]}})})
    assert refined['matched_count']==0 and refined['query']['joins']==result['query']['joins']
    matches=api('/api/v1/places/search?q='+requests.utils.quote('hẻm 114 Trần Quốc Tuấn Gò Vấp'))['results']
    place=api('/api/v1/places/detail?place_id='+requests.utils.quote(matches[0]['id']))
    selected=tool('area_select',{'source':'search_place'},{'selected_place':place})
    assert selected['scope_summary']['kind']=='selected_place_buffer'
    assert not selected['scope_summary']['administrative_boundary'] and selected['radius_m']==1000
    viewport=selected['bbox'];evidence['go_vap_viewport']=viewport;evidence['selected_place']=place;save()
    plots=tool('dataset_query',{'query_json':json.dumps({'layer':'parcels','where':{'field':'area_m2','op':'between','value':[80,200]},
        'order_by':[{'field':'area_m2','direction':'asc'}],'limit':2})})
    assert plots['returned']==2
    ids=[row['id'] for row in plots['rows']]
    access=tool('accessibility_compare',{'parcel_ids':ids,'categories':['hospital','park'],'travel_mode':'car','radius_m':3000})
    available=[(r,c) for r in access['rows'] for c,a in r['amenities'].items() if a['status']=='available']
    assert available,'No real sourced route in acceptance case'
    row,category=available[0]
    route=tool('route_show',{'accessibility_id':access['id'],'parcel_id':row['parcel_id'],'category':category})
    assert route['geometry']['type']=='LineString' and len(route['geometry']['coordinates'])>=2
    assessment=tool('candidate_compare',{'parcel_ids':ids,'population_year':2026,'travel_mode':'car',
        'criteria_json':json.dumps([{'metric':'area_m2','direction':'maximize','weight':50},
                                   {'metric':'hospital_travel_seconds','direction':'minimize','weight':50}])})
    assert 'hospital_travel_seconds' in assessment['common_scored_metrics']
    report=tool('urban_report',{})
    assert access['id'] in report['markdown'] and 'Goong' in report['markdown']
    model_cases(evidence,viewport,place)


def model_cases(evidence,viewport,place,resume=False):
    def save():
        OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    if not resume:evidence['model_session_id']=api('/api/v1/agent/sessions',{})['session_id'];save()
    prompts=[
        'Within the visible map, find source parcels of 80–200 m² near a road with a residential reference land price of 20–40 million VND/m² within 300 m. Show at most 3 smallest parcels and count ALL matching installed records before the display limit. Preserve source review flags and clarify road references are not parcel market values.',
        'Tiếp tục trong vùng này. Tạo truy vấn MỚI bỏ điều kiện giá và khoảng cách tới đường giá, giữ diện tích 80–200 m². Hiển thị đúng 2 thửa nhỏ nhất, kèm số lượng khớp trước giới hạn hiển thị.',
        'For those two parcels, compare driving travel times by car to mapped hospitals and parks within a 3 km POI discovery radius. Then display a sourced route to the hospital for the FIRST parcel from the previous query. State the source and limits; do not substitute straight-line distances for driving routes.'
    ]
    first_id=None
    existing=len(evidence['turns']) if resume else 0
    for index,prompt in enumerate(prompts):
        if index<existing:value=evidence['turns'][index]['response']
        else:
            value=api('/api/v1/agent/chat',{'session_id':evidence['model_session_id'],'request_id':str(uuid4()),
                'message':prompt,'workspace':{'viewport':viewport,'selected_place':place},'allow_native':False})
            evidence['turns'].append({'prompt':prompt,'response':value});save()
        if index<2:
            latest=value['structured_queries'][-1]
            assert latest['query_engine']=='postgis'
            assert latest['returned']<=(3 if index==0 else 2)
            assert all(80<=r['area_m2']<=200 for r in latest['rows'])
            if index==0:
                assert latest['query']['joins'] and latest['query']['joins'][0]['required']
                expression=latest['query']['joins'][0]['where']
                for amount,expected in [(19999999,False),(20000000,True),(30000000,True),(40000000,True),(40000001,False)]:
                    assert evaluate(expression,{'residential_vnd_m2':amount,'unit':'VND/m2','id':'probe'}) is expected,expression
            else:
                assert not latest['query']['joins'] and latest['returned']==2
                first_id=latest['rows'][0]['id']
        else:
            assert value['route_result']['parcel_id']==first_id
            assert value['route_result']['category']=='hospital'
            assert value['route_result']['source']=='Goong Directions V2'
            assert value['route_features']['features'][0]['geometry']['type']=='LineString'
        assert hint(value['answer'])==('Vietnamese' if index==1 else 'English'),value['answer']
    evidence['passed']=True;save()
    print(json.dumps({'passed':True,'model_traces':[turn['response']['trace'] for turn in evidence['turns']],'evidence':str(OUT)},ensure_ascii=False))


if __name__=='__main__':
    if '--resume-model' in sys.argv:
        evidence=json.loads(OUT.read_text(encoding='utf-8'))
        model_cases(evidence,evidence['go_vap_viewport'],evidence['selected_place'],resume=True)
    elif '--model-only' in sys.argv:
        evidence=json.loads(OUT.read_text(encoding='utf-8'))
        evidence.setdefault('prior_attempts',[]).append(evidence.get('turns',[]))
        evidence['turns']=[];evidence.pop('passed',None)
        model_cases(evidence,evidence['go_vap_viewport'],evidence['selected_place'])
    else:main()
