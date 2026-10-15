"""Local browser fixture server; never imported by the production application.

Run with an isolated ZONING_DATA_DIR, PYTHONPATH=backend;etl;backend/tests.
Parcel and generated building sources are fixtures; commands, geometry, persistence and locks are real.
"""
from copy import deepcopy

from app.main import app  # noqa: F401
from app.routers import zoning
from app.services.zoning import baseline, development

PARCEL = {"id": "3885881", "land_use": "ODT", "geometry": {"type": "Polygon", "coordinates": [
    [[106.7605, 10.8205], [106.762, 10.8205], [106.762, 10.822], [106.7605, 10.822], [106.7605, 10.8205]]
]}}
original_selected_parcel = zoning.selected_parcel


def selected_parcel(plan, identifier):
    if identifier == PARCEL["id"]:
        return plan.get("parcels", {}).get(identifier) or development.parcel_snapshot(plan, deepcopy(PARCEL))
    return original_selected_parcel(plan, identifier)


zoning.selected_parcel = selected_parcel

baseline.buildings = lambda parcel, study: [{'id':'fixture-generated', 'geometry': {'type':'Polygon','coordinates':[
    [[106.761,10.821],[106.7614,10.821],[106.7614,10.8214],[106.761,10.8214],[106.761,10.821]]]},
    'height_m':12.8,'floors':4,'space_use_id':'residential','source':'Fixture generated buildings'}] if parcel['id'] == PARCEL['id'] or parcel['id'].startswith('zone:') else None

# Keep browser tests offline. This fixture module is never imported by production.
def fixture_road_context(region, radius_m):
    import hashlib
    import json
    from app.services.zoning import simulation_context
    west,south,east,north=region.bounds
    west-=.008; south-=.008; east+=.008; north+=.008
    nodes=[]; ways=[]
    for row in range(8):
        for col in range(8):
            nodes.append({'type':'node','id':row*8+col+1,
                          'lon':west+(east-west)*col/7,'lat':south+(north-south)*row/7})
    for row in range(8):
        for col in range(8):
            a=row*8+col
            for b in ([a+1] if col<7 else [])+([a+8] if row<7 else []):
                ways.append({'type':'way','id':len(ways)+1,'nodes':[nodes[a]['id'],nodes[b]['id']],
                             'geometry':[{'lon':nodes[i]['lon'],'lat':nodes[i]['lat']} for i in (a,b)],
                             'tags':{'highway':'residential','lanes':'2','maxspeed':'30'}})
    document={'schema_version':1,'bbox':[west,south,east,north],'osm':{'elements':nodes+ways},
              'source':'SYNTHETIC offline browser-test grid, not actual OSM',
              'captured_at':None,'radius_m':radius_m,'network_kind':'synthetic_test_fixture'}
    raw=json.dumps(document,sort_keys=True,separators=(',',':')).encode()
    identifier=hashlib.sha256(raw).hexdigest()
    simulation_context.directory().mkdir(parents=True,exist_ok=True)
    (simulation_context.directory()/(identifier+'.json')).write_bytes(raw)
    return identifier,document

from app.services.zoning import simulation_context
simulation_context.acquire_network=fixture_road_context
