"""Real dataset and natural-language regression for prices/house amenity search."""
import json
from pathlib import Path
from uuid import uuid4

import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'test-results/general-agent/datasets-result.json'
BASE='http://127.0.0.1:8192'


def api(path, body):
    response=requests.post(BASE+path,json=body,timeout=180)
    response.raise_for_status()
    return response.json()


def main():
    viewport=json.loads((ROOT/'test-results/general-agent/live-result.json').read_text(encoding='utf-8'))['viewport']
    binding={'viewport':viewport}
    poi_evidence=ROOT/'test-results/general-agent/system-pois-browser.json'
    if poi_evidence.is_file():
        binding['map_pois']=json.loads(poi_evidence.read_text(encoding='utf-8'))['workspace']['map_pois']
    session=api('/api/v1/agent/sessions',{})
    sid=session['session_id']
    evidence={'session_id':sid,'viewport':viewport,'map_poi_count':len(binding.get('map_pois',{}).get('features',[])),'tools':[],'turns':[]}
    def save():
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    def tool(name,args):
        value=api(f'/api/v1/agent/sessions/{sid}/tools/{name}',{'arguments':args,'workspace':binding})
        evidence['tools'].append({'name':name,'response':value});save()
        return value['tool_result']
    tool('area_select',{'source':'viewport'})
    price=tool('layer_query',{'layer':'land_price','radius_m':1000,'parcel_id':None,'text':None,'start_date':None,'end_date':None})
    assert 'metadata' in price and 'records' in price
    amenities=tool('amenity_site_search',{'requirements_json':'{"supermarket":1000,"park":1000,"hospital":2000}',
        'household_people':4,'minimum_area_m2':None,'maximum_area_m2':None,'bbox':None,'limit':3})
    assert 'OpenStreetMap' in amenities['amenity_source']['source']
    assert amenities['sample_size']>0
    assert amenities['household_people']==4
    for prompt,expected in [
        ('What are the land price references in the selected area? Show prices, units and effective dates.','layer_query'),
        ('Find me a place to build a house for 4 people in the currently selected area. It should be near supermarkets, parks, and hospital.','amenity_site_search')]:
        value=api('/api/v1/agent/chat',{'session_id':sid,'request_id':str(uuid4()),'workspace':binding,
                                    'message':prompt,'allow_native':False})
        evidence['turns'].append({'prompt':prompt,'response':value});save()
        assert any(t['tool']==expected and t['status']=='succeeded' for t in value['trace']),value['trace']
    print(json.dumps({'passed':True,'price_records':len(price['records']),
        'amenity_search_status':amenities['status'],'sample_size':amenities['sample_size'],
        'matches_in_sample':amenities['matching_in_sample'],
        'turns':[{'prompt':t['prompt'],'answer':t['response']['answer'],'trace':t['response']['trace']} for t in evidence['turns']]},ensure_ascii=False))


if __name__=='__main__':main()
