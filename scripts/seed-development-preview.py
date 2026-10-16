"""Create an actual parcel case on the ISOLATED preview, then run its public API."""
import argparse
import json
from pathlib import Path
import time
import sys
from uuid import uuid4

import requests
from shapely.geometry import shape, box, mapping

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8192')
parser.add_argument('--mode',choices=['screening','native'],default='native')
parser.add_argument('--resume',action='store_true')
parser.add_argument('--collect',action='store_true',help='Read an existing job; never submit another run')
args=parser.parse_args()
out=ROOT/'test-results'/'development-context'
out.mkdir(parents=True,exist_ok=True)
file=out/('live-'+args.mode+'.json')
error_file=out/('live-'+args.mode+'-error.json')
if error_file.exists():
    error_file.unlink()
session=requests.Session()
def failure(kind,error,traceback):
    (out/('live-'+args.mode+'-error.json')).write_text(json.dumps({'type':kind.__name__,'error':str(error)[:1000]}))
    sys.__excepthook__(kind,error,traceback)
sys.excepthook=failure
for attempt in range(30):
    try:
        if session.get(args.url+'/health',timeout=3).ok:
            break
    except requests.RequestException:
        pass
    time.sleep(2)
else:
    raise RuntimeError('Separate preview is not healthy')


def request(path,data=None):
    response=session.request('GET' if data is None else 'POST',args.url+'/api/v1'+path,json=data,timeout=65)
    if not response.ok:
        raise RuntimeError(str(response.status_code)+' '+response.text[:500])
    return response.json()


if args.collect:
    record=json.loads(file.read_text())
    job=request('/planning/jobs/'+record['job']['id'])
    record['job']=job
    if job.get('result_id'):
        record['result']=request('/planning/runs/'+job['result_id'])
    record['children']=request('/planning/jobs/'+job['id']+'/children')['children']
    record['elapsed_seconds']=job['heartbeat']-job['created_at']
    file.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(json.dumps({'status':job['status'],'elapsed_seconds':record['elapsed_seconds'],'result_id':job.get('result_id')}))
    sys.exit(0 if job['status']=='succeeded' else 1)


snapshot=ROOT.parent/'UrbanDynamics'/'.runtime'/'planning-system'/'snapshots'/'0e62caa68cf5d4a1c9941cd82d59b8d4a09a453170dd09726c322d252bea2fda.json'
document=json.loads(snapshot.read_text())
feature=next(f for f in document['parcels']['features'] if str(f['id'])=='1937203')
parcel=shape(feature['geometry'])
if parcel.geom_type=='MultiPolygon':
    assert len(parcel.geoms)==1
    parcel=parcel.geoms[0]
west,south,east,north=parcel.bounds
region=box(west-.001,south-.001,east+.001,north+.001)
inner=parcel.buffer(-.00003)
point=(inner if not inner.is_empty else parcel).representative_point()
footprint=box(point.x-.00008,point.y-.00008,point.x+.00008,point.y+.00008).intersection(parcel.buffer(-.000001))
assert footprint.geom_type=='Polygon' and footprint.area>0
if args.resume and file.is_file():
    previous=json.loads(file.read_text())
    if previous.get('job') and request('/planning/jobs/'+previous['job']['id'])['status'] in ('queued','running','succeeded'):
        raise RuntimeError('Existing job is active or complete; do not submit a duplicate')
    plan=request('/zoning/plans/'+previous['plan']['id'])
    scenario=plan['scenarios'][1]
else:
    plan=request('/zoning/plans',{'name':'Simulation context demo · Thu Duc parcel 1937203',
                               'description':'Separate preview: sourced local OSM, labelled traffic and surface assumptions.',
                               'study_area':mapping(region)})
    scenario=plan['scenarios'][1]
    plan=request('/zoning/plans/'+plan['id']+'/commands',{'revision':plan['revision'], 'scenario_id':scenario['id'],
        'action':'save_building','payload':{'parcel_id':'1937203','name':'Apartment proposal · 4 floors',
            'geometry':mapping(footprint),'floors':4,'floor_height':3.2,'space_use_id':'residential'}})
settings={'residential_m2_per_person':35,'work_m2_per_staff':20,'visitors_per_100m2_day':10,
          'green_open_percent':30,'rainfall_mm':60,'landscape_mode':'preserve','traffic_radius_m':750}
record={'url':args.url,'plan':plan,'settings':settings,'parcel_id':'1937203','mode':args.mode}
file.write_text(json.dumps(record,ensure_ascii=False,indent=2))
start=time.monotonic()
submitted=request('/zoning/plans/'+plan['id']+'/simulation/runs',{
    'revision':plan['revision'],'scenario_id':scenario['id'],'parcel_id':'1937203',
    **settings,'mode':args.mode,'idempotency_key':str(uuid4())})
record.update(study=submitted['study'],job=submitted['job'],preparation_seconds=time.monotonic()-start)
file.write_text(json.dumps(record,ensure_ascii=False,indent=2))
print(json.dumps({'plan_id':plan['id'],'job_id':record['job']['id'],'mode':args.mode,'preparation_seconds':record['preparation_seconds']}),flush=True)
deadline=time.monotonic()+1500
while time.monotonic()<deadline:
    job=request('/planning/jobs/'+record['job']['id'])
    record['job']=job
    if job['status'] not in ('queued','running'):
        record['elapsed_seconds']=time.monotonic()-start
        if job['result_id']:
            result=request('/planning/runs/'+job['result_id'])
            record['result']=result
        file.write_text(json.dumps(record,ensure_ascii=False,indent=2))
        print(json.dumps({'status':job['status'],'elapsed_seconds':record['elapsed_seconds'],'error':job.get('error')}),flush=True)
        assert job['status']=='succeeded',job.get('error')
        break
    time.sleep(3)
else:
    raise RuntimeError('Preview wait limit reached; check the saved job ID before retrying')
