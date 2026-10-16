"""Exercise every published layer adapter against the preview, read-only sources."""
import json
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8192'
OUT=ROOT/'test-results/general-agent/layer-matrix.json'


def main():
    viewport=json.loads((ROOT/'test-results/general-agent/live-result.json').read_text(encoding='utf-8'))['viewport']
    session=requests.post(BASE+'/api/v1/agent/sessions',json={},timeout=30).json()
    sid=session['session_id']
    def call(name,args):
        response=requests.post(BASE+f'/api/v1/agent/sessions/{sid}/tools/{name}',
            json={'arguments':args,'workspace':{'viewport':viewport}},timeout=45)
        return response
    call('area_select',{'source':'viewport'}).raise_for_status()
    response=call('source_catalog',{});response.raise_for_status()
    catalog=response.json()['tool_result'];rows=[]
    for entry in catalog['queryable_layers']:
        response=call('layer_query',{'layer':entry['id'],'radius_m':0,'population_year':2026,
                                     'traffic_weekday':2,'traffic_hour':18})
        data=response.json()
        value=data.get('tool_result',{})
        rows.append({'layer':entry['id'],'http_status':response.status_code,'status':value.get('status'),
            'returned':len(value.get('records',[])),'metadata':value.get('metadata'),
            'first_record':value.get('records',[None])[0] if value.get('records') else None,
            'detail':data.get('detail')})
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps({'session_id':sid,'viewport':viewport,'catalog':catalog,'layers':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'layer':r['layer'],'http_status':r['http_status'],'status':r['status'],
                       'returned':r['returned'],'detail':r['detail']} for r in rows],ensure_ascii=False))


if __name__=='__main__':main()
