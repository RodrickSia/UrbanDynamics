"""Preview-only live dataset/tool and real-model query regression; saves evidence."""
import json
from pathlib import Path
from uuid import uuid4

import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results/general-agent/structured-query-result.json'
BASE='http://127.0.0.1:8192'


def api(path,body):
    r=requests.post(BASE+path,json=body,timeout=180)
    if not r.ok:raise RuntimeError(f'{r.status_code}: {r.text[:800]}')
    return r.json()


def main():
    viewport=json.loads((ROOT/'test-results/general-agent/live-result.json').read_text(encoding='utf-8'))['viewport']
    sid=api('/api/v1/agent/sessions',{})['session_id']
    evidence={'session_id':sid,'viewport':viewport,'tools':[],'turns':[]}
    def save():
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    def tool(name,args):
        value=api(f'/api/v1/agent/sessions/{sid}/tools/{name}',{'arguments':args,'workspace':{'viewport':viewport}})
        evidence['tools'].append({'name':name,'response':value});save()
        return value['tool_result']
    tool('area_select',{'source':'viewport'})
    for layer in ('parcels','land_price','poi','traffic'):
        value=tool('dataset_describe',{'layer':layer})
        assert value['layer']==layer
    price=tool('dataset_query',{'query_json':json.dumps({'layer':'land_price',
        'where':{'field':'residential_vnd_m2','op':'between','value':[20000000,40000000]},
        'order_by':[{'field':'residential_vnd_m2','direction':'asc'}],
        'select':['residential_vnd_m2'], 'aggregates':[{'op':'count'},{'op':'avg','field':'residential_vnd_m2'}]})})
    assert all(20000000<=r['residential_vnd_m2']<=40000000 for r in price['rows'])
    if price['rows']:
        assert 'geometry_reviewed' in price['rows'][0]
    joined=tool('dataset_query',{'query_json':json.dumps({'layer':'parcels',
        'joins':[{'layer':'land_price','alias':'price','radius_m':300,
                  'where':{'field':'residential_vnd_m2','op':'between','value':[20000000,40000000]}}],
        'where':{'field':'price.observed_match','op':'eq','value':True},
        'select':['area_m2','price.distance_m','price.residential_vnd_m2'],
        'order_by':[{'field':'area_m2','direction':'asc'}],'limit':3})})
    assert joined['returned']<=3
    assert all(r['price.distance_m']<=300 for r in joined['rows'])
    refined=tool('dataset_query_refine',{'query_id':joined['id'],
        'patch_json':json.dumps({'where':{'field':'area_m2','op':'between','value':[40,1000]}})})
    assert all(40<=r['area_m2']<=1000 for r in refined['rows'])
    assert refined['parent_query_id']==joined['id']
    report=tool('urban_report',{})
    assert refined['id'] in report['markdown']
    model_sid=api('/api/v1/agent/sessions',{})['session_id']
    evidence['model_session_id']=model_sid;save()
    prompts=[
        'Within the visible map, find source parcels of 40 to 1000 square metres within 300 metres of a road with a residential reference land price between 20 and 40 million VND per square metre. Return up to 3, sorted by parcel area ascending. Query the connected datasets, show the source review flags and clarify this is not a verified parcel market price.',
        'Tiếp tục lọc các kết quả này: chỉ lấy diện tích từ 80 đến 500 m². Giữ điều kiện giá và khoảng cách trước đó, cho biết có bao nhiêu bản ghi khớp trong dữ liệu đã fetch.',
        'Trong cùng khu vực này, tạo truy vấn mới bỏ giới hạn diện tích. Tìm parcel trong bán kính 300 m của đường có giá đất ở tham chiếu 20–40 triệu VND/m². Hiển thị 3 thửa có diện tích nhỏ nhất, kèm khoảng cách, nguồn và cờ rà soát; đếm số bản ghi khớp. Không coi đây là giá thị trường của thửa.'
    ]
    for i,prompt in enumerate(prompts):
        value=api('/api/v1/agent/chat',{'session_id':model_sid,'request_id':str(uuid4()),
             'message':prompt,'workspace':{'viewport':viewport},'allow_native':False})
        evidence['turns'].append({'prompt':prompt,'response':value});save()
        successful={t['tool'] for t in value['trace'] if t['status']=='succeeded'}
        assert ('dataset_query_refine' if i==1 else 'dataset_query') in successful,value['trace']
        assert value['structured_queries'],value['answer']
        latest=value['structured_queries'][-1]
        assert latest['matched_in_bounded_fetch']==(joined['matched_in_bounded_fetch'] if i==2 else 0),latest['query']
        assert all(j['required'] for j in latest['query']['joins']),latest['query']
        if i==2:
            assert latest['returned']==3,value['answer']
    evidence['passed']=True;save()
    print(json.dumps({'passed':True,'price_matches':price['matched_in_bounded_fetch'],
       'joined_matches':joined['matched_in_bounded_fetch'],'refined_matches':refined['matched_in_bounded_fetch'],
       'model_turns':[{'trace':t['response']['trace'],'answer':t['response']['answer']} for t in evidence['turns']],
       'evidence':str(OUT)},ensure_ascii=False))


if __name__=='__main__':main()
