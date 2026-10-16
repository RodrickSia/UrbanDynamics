"""Resolve named streets/alleys using the system's actual OSM/SUMO road data."""
import json
import re
import unicodedata

from shapely.geometry import mapping,shape
from shapely.ops import transform

from app.services.simulation.integrated.context import projection
from src.shared.database import connect_to_warehouse,warehouse_configured

ACCENTS='àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
PLAIN=''.join('d' if c=='đ' else unicodedata.normalize('NFD',c)[0] for c in ACCENTS)


def normalize(value):
    value=re.sub(r'\bđường\s+','',value.casefold())
    value=re.sub(r'^(duong|phố|pho)\s+','',value)
    value=''.join(c for c in unicodedata.normalize('NFD',value.replace('đ','d')) if not unicodedata.combining(c))
    value=re.sub(r'[^a-z0-9 /-]',' ',value)
    value=re.sub(r'\s+',' ',value).strip()
    return value


def road_rows(query,bbox=None):
    if not warehouse_configured():raise ValueError('Named street lookup needs the connected road warehouse')
    text=normalize(query)
    if len(text)<4 or len(text)>160 or len(text.split())<2:
        raise ValueError('Provide a street/alley name without building-plan instructions')
    normalized="translate(lower(name),%s,%s)"
    spatial=' AND geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)' if bbox else ''
    arguments=[ACCENTS,PLAIN,'%'+ '%'.join(text.split())+'%']
    if bbox:arguments.extend(bbox)
    arguments.extend([ACCENTS,PLAIN,text])
    with connect_to_warehouse() as connection:
        connection.execute('SET LOCAL statement_timeout=12000')
        rows=connection.execute('''SELECT name,ST_AsGeoJSON(ST_Collect(geom)),count(*) FROM transport.sumo_edge
            WHERE geom IS NOT NULL AND '''+normalized+''' LIKE %s'''+spatial+'''
            GROUP BY name ORDER BY CASE WHEN '''+normalized+''' = %s THEN 0 ELSE 1 END,name LIMIT 12''',arguments).fetchall()
    return rows


def matches(query,bbox=None,radius_m=100):
    records=road_rows(query,bbox)
    output=[]
    for name,raw,count in records:
        geometry=shape(json.loads(raw) if isinstance(raw,str) else raw)
        forward,inverse=projection(geometry)
        metric=transform(forward,geometry)
        # Separate distant homonyms instead of combining them into a giant study area.
        clusters=metric.buffer(35)
        parts=list(clusters.geoms) if clusters.geom_type=='MultiPolygon' else [clusters]
        for cluster in parts[:8]:
            segments=metric.intersection(cluster)
            selected=transform(inverse,segments.buffer(radius_m))
            output.append({'name':name,'geometry':mapping(selected),'road_geometry':mapping(transform(inverse,segments)),
                'bbox':list(selected.bounds),'source_segment_count_for_name':int(count),
                'match_kind':'exact_name' if normalize(name)==normalize(query) else 'partial_name',
                'radius_m':radius_m,'source':'Team transport.sumo_edge / sourced OSM road geometry'})
    exact=[m for m in output if m['match_kind']=='exact_name']
    # Do not substitute 114/2 or 114/14 when the exact alley 114 exists.
    selected=exact if exact else output
    return [{**value,'index':i} for i,value in enumerate(selected[:8])]


def select(session,args):
    from .general_tools import bounds,now
    from uuid import uuid4
    query=(args.get('query') or '').strip()
    bbox=list(bounds(args['bbox']).bounds) if args.get('bbox') else None
    options=matches(query,bbox)
    if not options:
        raise ValueError('No named road/alley match in the connected road data. Try area_select place, provide a map pin/bbox, or select the location on the map; do not invent coordinates.')
    public=[{k:v for k,v in option.items() if k not in ('geometry','road_geometry')} for option in options]
    if len(options)>1 and args.get('match_index') is None:
        return {'status':'ambiguous_street','street_matches':public,'action':'Ask the user to choose a matching street/extent before searching parcels. Analysis area has not changed.'}
    index=int(args.get('match_index') or 0)
    if not 0<=index<len(options):raise ValueError('Choose one returned street match index')
    match=options[index]
    session['analysis_area']={'id':uuid4().hex,'title':match['name']+' · within 100 m of mapped street',
        'geometry':match['geometry'],'bbox':match['bbox'],'source':match['source'],
        'street_name':match['name'],'target_street_geometry':match['road_geometry'],'street_radius_m':100,
        'match_kind':match['match_kind'],'selected_at':now(),
        'location_precision':'Mapped street/alley centerline buffer, not an exact house/parcel address, legal alley boundary or administrative boundary'}
    session['map_actions'].append({'type':'focus','bbox':match['bbox']})
    return {**session['analysis_area'],'status':'street_selected','street_matches':public,
        'next':'Search source parcels in this area. Keep proposed floor count separate from verified zoning permission; vacancy and land rights remain unknown.'}
