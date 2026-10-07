"""Build the approved analytical union from OCHA/HDX COD boundaries."""
import argparse
import json
from pathlib import Path
import sys
import zipfile
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union

from src.shared.data_io import data_dir,session,download,read_json,write_json,file_provenance
from src.pipelines.flood_history.transform import normalize
from src.shared.database import publish
from src.pipelines.rainwater.config import SCOPE

CATALOG = 'https://data.humdata.org/api/3/action/package_show?id=cod-ab-vnm'
DATASET = 'https://data.humdata.org/dataset/cod-ab-vnm'
ALIASES = {'hochiminh':'hcmc_previous','tp.hochiminh':'hcmc_previous',
           'hochiminhcity':'hcmc_previous','thanhphohochiminh':'hcmc_previous',
           'binhduong':'binh_duong_previous','bariavungtau':'ba_ria_vung_tau_previous'}

def build(document,metadata):
    selected = []
    for feature in document['features']:
        names = [normalize(v) for k,v in feature['properties'].items()
                 if isinstance(v,str) and ('adm1' in k.lower() or k.lower() in ('shapename','name_1','name'))]
        region = next((ALIASES[n] for n in names if n in ALIASES),None)
        if region:
            geometry = shape(feature['geometry'])
            if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ('Polygon','MultiPolygon'):
                raise ValueError('Invalid province polygon; do not silently repair source')
            selected.append({'type':'Feature','id':region,'geometry':mapping(geometry),
                'properties':{'region_id':region,'source_attributes':feature['properties'],'source_url':DATASET}})
    already_merged = len(selected)==1 and selected[0]['id']=='hcmc_previous'
    if not already_merged and (len(selected)!=3 or len({f['id'] for f in selected})!=3):
        raise ValueError('Expected three pre-merger provinces or a verified post-merger HCMC polygon')
    geometry = unary_union([shape(f['geometry']) for f in selected])
    checks = {'Ho Chi Minh':(106.7,10.78),'Binh Duong':(106.66,11.1),
              'Vung Tau':(107.084,10.35),'Con Dao':(106.609,8.683)}
    if not geometry.is_valid or not all(geometry.covers(Point(p)) for p in checks.values()):
        raise ValueError('Boundary must cover all three regions INCLUDING Con Dao')
    if already_merged:
        selected[0]['id'] = 'hcmc_expanded'
        selected[0]['properties']['region_id'] = 'hcmc_expanded'
    return {'type':'FeatureCollection','features':[{'type':'Feature','id':'hcmc-expanded',
        'geometry':mapping(geometry),'properties':{'name':SCOPE}}],
        'metadata':{**metadata,'scope':SCOPE,
                    'legal_boundary':False,'includes_con_dao':True,
                    'method':'verified_post_merger_source' if already_merged else 'union_of_three_pre_merger_provinces'}},selected

def run(cached=False):
    raw = data_dir()/'raw/boundaries'
    catalog = raw/'hdx-cod-ab-vnm.json'; archive = raw/'hdx-vnm-boundaries.geojson.zip'
    if not cached or not catalog.exists():
        response = session().get(CATALOG,timeout=(20,90)); response.raise_for_status()
        body = response.json()
        if not body.get('success'): raise ValueError('HDX catalog unavailable')
        write_json(catalog,body['result'])
    info = read_json(catalog)
    resource = next(r for r in info['resources'] if r.get('name','').endswith('geojson.zip'))
    if not cached or not archive.exists(): download(resource['url'],archive,max_bytes=250_000_000)
    with zipfile.ZipFile(archive) as bundle:
        names = [n for n in bundle.namelist() if n.lower().endswith('.geojson') and ('adm1' in n.lower() or 'admin1' in n.lower())]
        if len(names)!=1: raise ValueError(f'Expected one ADM1 file: {bundle.namelist()}')
        if bundle.getinfo(names[0]).file_size>150_000_000: raise ValueError('ADM1 file too large')
        with bundle.open(names[0]) as stream: document = json.load(stream)
    metadata = {'source_url':DATASET,'source_resource_url':resource['url'],
        'license':info.get('license_title'),'source_notes':info.get('notes'),
        'source_metadata_created':info.get('metadata_created'),'source_metadata_modified':info.get('metadata_modified'),
        'source_extras':info.get('extras'),'provenance':[file_provenance(archive,resource['url'])]}
    boundary,regions = build(document,metadata)
    target = data_dir()/'inputs/hcmc_expanded_boundary.geojson'
    write_json(target,boundary)
    publish('hcmc_boundary',boundary)
    publish('hcmc_regions',{'type':'FeatureCollection','features':regions,'metadata':metadata|{'scope':SCOPE}})
    print(json.dumps({'boundary':str(target),'includes_con_dao':True,
                      'bounds':shape(boundary['features'][0]['geometry']).bounds},ensure_ascii=False))
