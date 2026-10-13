"""Actual sourced parcels, equal-program comparison and cumulative native job."""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx
from shapely.geometry import shape
from shapely.ops import transform

import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'backend'),str(Path(__file__).resolve().parents[1]/'etl')]
from app.services.simulation.integrated.context import projection


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('test-results/planning-system-multisite'))
    parser.add_argument('--network-mode',choices=['osm_snapshot','synthetic_corridor'],default='osm_snapshot')
    parser.add_argument('--with-counting',action='store_true')
    args=parser.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    with httpx.Client(base_url='http://127.0.0.1:8007/api/v1/planning',timeout=60) as c:
        response=c.get('/demo/system/snapshots');response.raise_for_status()
        snapshot=max(response.json()['snapshots'],key=lambda s:s['captured_at'])
        response=c.get('/demo/system/snapshots/'+snapshot['id']+'/parcels');response.raise_for_status()
        features=response.json()['features'];selected=[]
        def priority(f):
            return (f['properties'].get('mdsdd')!='ODT',f['demo_area_m2'])
        for f in sorted(features,key=priority):
            if not 1500<=f['demo_area_m2']<=15000:
                continue
            geom=shape(f['geometry']);forward,_=projection(geom)
            box=list(transform(forward,geom).minimum_rotated_rectangle.exterior.coords)
            sides=[((box[i+1][0]-box[i][0])**2+(box[i+1][1]-box[i][1])**2)**.5 for i in range(2)]
            if max(sides)/min(sides)>3 or min(sides)<25:
                continue
            if any(geom.intersection(shape(other['geometry'])).area>1e-12 for other in selected):
                continue
            selected.append(f)
            if len(selected)==3:
                break
        assert len(selected)==3,'Need three suitable distinct parcel geometries'
        request={'snapshot_id':snapshot['id'],'parcel_ids':[str(f['id']) for f in selected],
            'traffic_network_mode':args.network_mode,
            'housing_units':20,'residents':60,'floors':4,'floor_area_m2':1600,
            'conditions':{'traffic_hours':[18],'seeds':[2026]}}
        if args.with_counting:
            response=c.get('/demo/system/traffic-default');response.raise_for_status()
            reference=response.json()
            # Omit both fields to verify the same automatic default as the UI.
        response=c.post('/demo/system/prepare',json={**request,'equal_program':True});response.raise_for_status()
        equal=response.json()['study']
        assert equal['comparison_policy']=='equal_program'
        assert all(p['development']['buildings'][0]['gross_floor_area_m2']==1600 for p in equal['projects'])
        response=c.post('/studies/preflight',json=equal);response.raise_for_status()
        (out/'equal-program-study.json').write_text(json.dumps(equal,ensure_ascii=False,indent=2),encoding='utf-8')
        response=c.post('/demo/system/prepare',json={**request,'mode':'cumulative'});response.raise_for_status()
        study=response.json()['study'];assert len(study['options'])==5 and len(study['phases'])==3
        response=c.post('/studies',json=study);response.raise_for_status();saved=response.json()
        response=c.post('/studies/'+saved['id']+'/runs',json={'mode':'native','idempotency_key':'multisite-'+uuid4().hex});response.raise_for_status();job=response.json()
        (out/'job.json').write_text(json.dumps(job,indent=2),encoding='utf-8');print(json.dumps({'job_id':job['id'],'parcels':request['parcel_ids']}),flush=True)
        deadline=time.monotonic()+900
        while True:
            response=c.get('/jobs/'+job['id']);response.raise_for_status();final=response.json()
            if final['status'] not in ('queued','running'):
                break
            if time.monotonic()>deadline:
                raise TimeoutError('Observe recorded job; do not restart it: '+job['id'])
            time.sleep(.5)
        assert final['status']=='succeeded',final
        response=c.get('/runs/'+final['result_id']);response.raise_for_status();result=response.json()
        all_built=next(o for o in result['options'] if o['id']=='together_3')
        assert all_built['state']['metrics']['housing_units']==60
        assert all_built['state']['metrics']['floor_area_m2']==4800
        assert all(result['validity'].values()),result['validity']
        assert result['context']['system_background']['parcel_bindings']=={'P'+str(i+1):str(f['id']) for i,f in enumerate(selected)}
        assert len(result['phases'])==3 and all(r['count_balanced'] for r in all_built['state']['traffic']['runs'])
        assert all_built['state']['drainage']['balance_passed']
        if args.with_counting:
            traffic=result['context']['resolved_background']['traffic']
            assert traffic['cars'][18]==round(reference['sample_vehicles_hour_by_class'].get('car',0))
            assert traffic['motorcycles'][18]==round(reference['sample_vehicles_hour_by_class'].get('motorcycle',0))
            assert result['context']['system_background']['counting_reference']['repaired_crossings']==reference['sample_crossings']
            assert study['traffic_prior']['counting_reference_id']==reference['counting_reference_id']
            assert study['traffic_prior']['source_kind']=='synthetic'
            assert result['context']['data_coverage']['observed_camera_counts'] is False
            assert all_built['state']['traffic']['runs'][0]['planned_vehicles']>=traffic['cars'][18]+traffic['motorcycles'][18]
        if args.network_mode=='osm_snapshot':
            assert all_built['state']['traffic']['runs'][0]['network_provenance']['kind']=='osm_topology_with_estimated_demand'
            assert any(f['properties']['source_kind']=='osm_topology' for f in result['spatial_artifacts']['roads']['features'])
        (out/'native-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        report={'status':'passed','job_id':job['id'],'run_id':result['id'],'parcel_ids':request['parcel_ids'],
            'network_mode':args.network_mode,
            'counting_reference_id':study.get('traffic_prior',{}).get('counting_reference_id'),
            'traffic_default':reference if args.with_counting else None,
            'parcel_properties':[f['properties'] for f in selected],'options':5,'phases':3,
            'checks':['three nonoverlapping real parcels','equal GFA/units/residents site comparison','individual and cumulative native states','SUMO count balance','SWMM balance','frozen actual parcel bindings'],
            'url':'http://127.0.0.1:8007/simulation/planning?job='+job['id']+'&option=together_3'}
        (out/'http-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
