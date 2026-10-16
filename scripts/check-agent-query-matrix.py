"""Exercise every web dataset through the structured query adapter, no model calls."""
import json
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8192/api/v1/agent'


def main():
    source=json.loads((ROOT/'test-results/general-agent/structured-query-result.json').read_text(encoding='utf-8'))
    sid=requests.post(BASE+'/sessions',json={},timeout=20).json()['session_id']
    def tool(name,args):
        return requests.post(BASE+f'/sessions/{sid}/tools/{name}',json={'arguments':args,
            'workspace':{'viewport':source['viewport']}},timeout=60)
    tool('area_select',{'source':'viewport'}).raise_for_status()
    results=[]
    for layer in ['population','flood_risk','flood_history','flood_satellite','land_price',
                  'parcels','synthetic_buildings','traffic','sumo_network','sumo_simulation','poi']:
        response=tool('dataset_query',{'query_json':json.dumps({'layer':layer,'limit':2,'aggregates':[{'op':'count'}]})})
        value=response.json()
        result=value.get('tool_result',{})
        results.append({'layer':layer,'status':response.status_code,'matched':result.get('matched_in_bounded_fetch'),
                        'returned':result.get('returned'),'sources':result.get('sources'),'error':value.get('detail')})
    output=ROOT/'test-results/general-agent/structured-query-matrix.json'
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'layer':v['layer'],'status':v['status'],'matched':v['matched'],'error':v['error']} for v in results]))
    assert all(v['status']==200 for v in results)


if __name__=='__main__':main()
