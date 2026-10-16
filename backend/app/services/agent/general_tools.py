"""Urban planning queries and multi-site studies, independent of an open Development plan.

All SQL identifiers are application-owned, values are bound, sources are explicit,
and suitability means a disclosed screening priority, never legal approval.
"""
import hashlib
import json
import math
import time
import threading
import os
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import requests
from fastapi import HTTPException
from psycopg import Error as DatabaseError
from pydantic import Field, model_validator
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union, polylabel
from shapely.affinity import rotate

from .models import Strict, Search
from .scope import metric_area, TO_METERS
from app import repository
from app.services import parcels
from app.services.zoning import simulation_context, baseline
from app.services.zoning.geometry import projected
from app.services.simulation.integrated.context import projection
from app.services.simulation.planning import store as runs
from app.services.simulation.planning.context import canonical_input, preflight
from app.services.simulation.planning.models import PlanningStudy
from src.shared.database import connect_to_warehouse, warehouse_configured

NAMES={'platform_overview','area_select','area_analyze','candidate_search','candidate_compare','layer_query','amenity_site_search',
       'dataset_describe','dataset_query','dataset_query_refine',
       'accessibility_compare','route_show',
       'planning_review','candidate_study_prepare','candidate_study_start','urban_results','urban_report'}
SCHEMA_VERSION='urban-agent-1'
GEOCODE_LOCK=threading.Lock()
LAST_GEOCODE=0.0
PLACE_CACHE={}


def now():
    return datetime.now(timezone.utc).isoformat()


def bounds(value):
    Search(bbox=value)
    if value is None:
        raise ValueError('No area chosen. Use a place name, map viewport, parcel, plan or explicit bbox.')
    region=box(*value)
    from .scope import metric_area
    if metric_area(region)>600_000_000:
        raise ValueError('Choose a smaller area (at most 600 km²); city-wide detailed analysis is bounded')
    return region


def selection(session):
    area=session.get('analysis_area')
    if area:
        return shape(area['geometry'])
    w=session.get('workspace',{})
    if w.get('plan_id'):
        from .development_tools import current
        plan,_=current(session)
        return shape(plan['study_area'])
    if w.get('viewport'):
        return bounds(w['viewport'])
    raise ValueError('Select an area first. You can analyze the visible map without opening a plan.')


def parcel(identifier):
    if not str(identifier).isdigit() or not 0<int(identifier)<=9223372036854775807:
        raise ValueError('Use an actual numeric source parcel ID')
    result=parcels.development_parcel(int(identifier))
    if not result:
        raise ValueError('Source parcel was not found')
    return result


def choose_area(session,args):
    global LAST_GEOCODE
    kind=args['source']
    note=''
    scope_kind=kind
    radius_m=None
    if kind=='street':
        from .street_location import select
        result=select(session,args)
        if result.get('status')!='ambiguous_street' and session.get('analysis_area'):
            from .scope import decorate
            session['analysis_area'].update(scope_kind='street_buffer',radius_m=100)
            decorate(session['analysis_area'])
            result.update(scope_summary=session['analysis_area']['scope_summary'])
            session.pop('query_features',None);session.pop('route_features',None)
        return result
    if kind=='search_place':
        from .layer_tools import buffered
        from shapely.geometry import Point
        hit=session.get('workspace',{}).get('selected_place')
        if not hit:raise ValueError('Select a real Search places result on the web first')
        region=buffered(Point(hit['longitude'],hit['latitude']),1000)
        title=hit.get('context') or hit['name']
        note='Selected web place coordinate; provisional 1000m point buffer, not administrative boundary'
        scope_kind='selected_place_buffer';radius_m=1000
    elif kind=='goong_place':
        from app.services import goong_places
        from .layer_tools import buffered
        from shapely.geometry import Point
        hits=goong_places.search(args.get('query') or '')['results']
        if not hits:raise ValueError('Goong found no matching place; use a map pin or another location')
        if args.get('match_index') is None and len(hits)>1:
            session['pending_goong_place']={'query':args.get('query'),'matches':hits}
            return {'status':'ambiguous_goong_place','matches':[{'index':i,**h} for i,h in enumerate(hits)],
                    'next':'Ask which match the user means before choosing a map area; no area was changed'}
        index=int(args.get('match_index') or 0)
        if not 0<=index<len(hits):raise ValueError('Choose one of the returned Goong place matches')
        hit=goong_places.detail(hits[index]['id'])
        region=buffered(Point(hit['longitude'],hit['latitude']),1000)
        title=hit['context'] or hit['name']
        note='Goong Places coordinate with an explicit provisional 1000m buffer; not a parcel or administrative boundary'
        scope_kind='goong_point_buffer';radius_m=1000
        alternatives=[{'index':i,**h} for i,h in enumerate(hits)]
        session.pop('pending_goong_place',None)
    elif kind=='place':
        query=(args.get('query') or '').strip()
        if len(query)<3 or len(query)>160:
            raise ValueError('Provide a public place/district name, not personal address data')
        cache=session.setdefault('place_cache',{})
        if query not in cache and query in PLACE_CACHE:
            cache[query]=PLACE_CACHE[query]
        if query not in cache:
            # Fixed provider, bounded response, no arbitrary URL tool exposed to the model.
            try:
                with GEOCODE_LOCK:
                    pause=1.05-(time.monotonic()-LAST_GEOCODE)
                    if pause>0:time.sleep(pause)
                    response=requests.get(os.getenv('AGENT_GEOCODER_URL','https://nominatim.openstreetmap.org/search'),params={'q':query,'format':'jsonv2','limit':3,'countrycodes':'vn','polygon_geojson':1},
                        headers={'User-Agent':'UrbanDynamics-MLAI2026/1.0 (https://github.com/RodrickSia/UrbanDynamics)'},timeout=(5,12))
                    LAST_GEOCODE=time.monotonic()
                response.raise_for_status()
                hits=response.json()
                if not isinstance(hits,list) or not hits:
                    raise ValueError('No location match; use the map viewport or a source parcel')
                cache[query]=hits[:3]
                PLACE_CACHE[query]=cache[query]
                if len(PLACE_CACHE)>128:PLACE_CACHE.pop(next(iter(PLACE_CACHE)))
            except (requests.RequestException,TypeError,json.JSONDecodeError):
                raise ValueError('Place lookup unavailable. Move the map to the area and use source=viewport.') from None
        hits=cache[query]
        index=int(args.get('match_index') or 0)
        if not 0<=index<len(hits):
            raise ValueError('Choose one of the returned place matches')
        hit=hits[index]
        south,north,west,east=map(float,hit['boundingbox'])
        region=bounds([west,south,east,north])
        note='Nominatim/OSM place bounding box, not a cadastral or legal district boundary'
        scope_kind='provider_place_bbox'
        geometry=hit.get('geojson')
        if isinstance(geometry,dict) and geometry.get('type') in ('Polygon','MultiPolygon') and len(json.dumps(geometry))<=1000000:
            candidate=shape(geometry)
            from .scope import metric_area
            if candidate.is_valid and not candidate.is_empty and 0<metric_area(candidate)<=600_000_000:
                region=candidate
                is_admin=hit.get('type')=='administrative' and hit.get('class',hit.get('category'))=='boundary'
                scope_kind='provider_administrative_polygon' if is_admin else 'provider_place_polygon'
                note='Nominatim/OSM provider '+('administrative' if is_admin else 'place')+' geometry; verify boundary vintage and applicability, not legal approval'
        title=hit.get('display_name',query)
        alternatives=[{'index':i,'name':h.get('display_name'),'boundingbox':h.get('boundingbox')} for i,h in enumerate(hits)]
    elif kind=='parcel':
        record=parcel(args.get('parcel_id'))
        region=shape(record['geometry']);title=f'Parcel {record["id"]}'
        note='Source parcel geometry from team warehouse'
    elif kind=='plan':
        from .development_tools import current
        plan,_=current(session);region=shape(plan['study_area']);title=plan['name'];note='Saved plan study area'
    else:
        region=bounds(args.get('bbox') if kind=='bbox' else session.get('workspace',{}).get('viewport'))
        title='Selected map area';note='Map/explicit bounding box; not an administrative boundary'
    session.pop('query_features',None)
    session.pop('route_features',None)
    from .scope import decorate
    session['analysis_area']=decorate({'id':uuid4().hex,'title':title,'geometry':mapping(region),'bbox':list(region.bounds),'source':note,'selected_at':now(),'scope_kind':scope_kind,'radius_m':radius_m})
    session['map_actions'].append({'type':'focus','bbox':list(region.bounds)})
    return {**session['analysis_area'],**({'place_matches':alternatives} if kind in ('place','goong_place') else {})}


def safe(operation):
    try:
        return operation()
    except (DatabaseError,OSError,ValueError,TypeError,KeyError,repository.LayerUnavailable,HTTPException):
        return None


def inventory(geometry):
    if not warehouse_configured():
        return {'status':'unknown'}
    with connect_to_warehouse() as c:
        c.execute('SET LOCAL statement_timeout=6000')
        if not c.execute("SELECT to_regclass('buildings.footprint')").fetchone()[0]:
            return {'status':'unknown'}
        row=c.execute('''WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) geom),
            b AS (SELECT ST_Intersection(f.geom,a.geom) geom FROM buildings.footprint f,a
                  WHERE f.geom && a.geom AND ST_Intersects(f.geom,a.geom) LIMIT 2001)
            SELECT count(*),ST_Area(ST_UnaryUnion(ST_Collect(geom))::geography) FROM b''',(json.dumps(geometry),)).fetchone()
    return {'status':'mapped_proxy' if row[0]<=2000 else 'truncated','mapped_count':row[0],
            'mapped_footprint_m2':float(row[1] or 0) if row[0]<=2000 else None,
            'source':'Team buildings.footprint / Overture','note':'Mapped detections, not surveyed occupancy/vacancy; zero matches does not prove empty land'}


def road_context(geometry):
    if not warehouse_configured():
        return None
    with connect_to_warehouse() as c:
        c.execute('SET LOCAL statement_timeout=5000')
        row=c.execute('''WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) geom)
            SELECT min(ST_Distance(e.geom::geography,a.geom::geography)),count(*)
            FROM transport.sumo_edge e,a WHERE e.geom && ST_Expand(a.geom,.012)
              AND ST_DWithin(e.geom::geography,a.geom::geography,1000)''',(json.dumps(geometry),)).fetchone()
    return {'nearest_mapped_road_m':float(row[0]) if row[0] is not None else None,'nearby_directed_edges':row[1],
            'source':'Team OSM-derived SUMO edges','kind':'access_proximity_proxy','note':'Straight-line distance, not a legal entrance, walking route or live traffic flow'}


def profile(region,year,include_traffic=True,traffic_weekday=2,traffic_hour=18,start=None,end=None):
    from app.services.area_indicators import sources, transit
    from app.services.simulation.integrated.background import osm_features
    geometry=mapping(region)
    area=metric_area(region)
    population=safe(lambda:sources.population(geometry,year))
    coverage=min(100,float(population['covered_m2'])/area*100) if population else None
    value=float(population['value']) if population and coverage>=99 else None
    building=safe(lambda:inventory(geometry)) or {'status':'unknown'}
    roads=safe(lambda:road_context(geometry)) or {'status':'unknown'}
    access=safe(lambda:transit.proximity(transform(TO_METERS,region),500)) or {'status':'unknown'}
    access.pop('geometry',None);access.pop('stops',None)
    layers={}
    for key in ('flood_history','flood_risk','flood_satellite','land_price','rainwater'):
        temporal=repository.LAYER_INFO.get(key,{}).get('time_enabled',False)
        result=safe(lambda:repository.features(key,list(region.bounds),start if temporal else None,end if temporal else None,limit=30))
        records=[] if result is None else [f for f in result.get('features',[]) if f.get('geometry') and shape(f['geometry']).intersects(region)]
        layers[key]={'status':'unavailable' if result is None else 'records_found' if records else 'no_matching_records',
            'records':[{'id':f.get('id'),'properties':f.get('properties',{})} for f in records[:5]],
            'matching_count_in_bounded_fetch':len(records),'query_limit':30,
            'metadata':result.get('metadata') if result else None,
            'requested_dates':{'start':str(start) if start else None,'end':str(end) if end else None,'filter_supported':temporal},
            'note':'Bounded records; no matches do not establish no hazard, low price or source completeness'}
    document=simulation_context.available_document(region)
    services={'status':'no_covering_snapshot','school_count':None,'source':None}
    green=None
    if document:
        facilities=osm_features(document.get('osm',{}))[2]
        forward,_=projection(region);buffered=transform(forward,region).buffer(1000)
        selected=[f for f in facilities if f.get('geometry') and transform(forward,shape(f['geometry'])).intersects(buffered)]
        services={'status':'snapshot_proxy','source':'Installed OSM snapshot','captured_at':document.get('captured_at'),
                  'mapped_facilities':[{'id':f.get('id'),'properties':f.get('properties')} for f in selected[:12]],
                  'school_count':sum(f.get('properties',{}).get('amenity') in ('school','kindergarten') for f in selected),
                  'available_seats':None,'note':'Mapped facilities within 1 km; completeness, enrollment and spare seats not verified'}
        parts=list(region.geoms) if region.geom_type=='MultiPolygon' else [region]
        if len(parts)<=20:
            surfaces=[simulation_context.surfaces(mapping(p),[],document)[1] for p in parts]
            green={'mapped_green_m2':sum(g.get('mapped_green_m2',0) for g in surfaces),
                   'unclassified_surface_m2':sum(g.get('unclassified_surface_m2',0) for g in surfaces),
                   'source':surfaces[0].get('landcover'),
                   'note':'Historical landcover and OSM, summed over disjoint parcel parts. This is ground context, not existing-building inventory integration.'}
    traffic=None
    if include_traffic:
        from app.routers.traffic import traffic_prediction
        from datetime import time as clock_time
        raw=safe(lambda:traffic_prediction(at=None,bbox=','.join(map(str,region.bounds)),limit=20,weekday=traffic_weekday,period=clock_time(traffic_hour)))
        if raw:
            traffic={'source':f'Historical typical congestion, ISO weekday {traffic_weekday}, {traffic_hour}:00; not live flow or building impact',
                     'metadata':raw.get('metadata'),'sample_edges':[{'id':f.get('id'),'properties':f.get('properties')} for f in raw.get('features',[])[:6]]}
    return {'area_m2':area,'queried_at':now(),'geometry':geometry,
            'population':{'year':year,'estimated_people':value,'covered_population':float(population['value']) if population else None,
                'coverage_percent':coverage,'density_people_km2':value/area*1e6 if value is not None else None,
                'source':'WorldPop area-weighted raster','kind':'modelled_population_not_census','files':population.get('files') if population else None},
            'buildings':building,'roads':roads,'transit':access,'services':services,'ground_cover':green,
            'layers':layers,'traffic':traffic,'capacity':{'water':None,'electricity':None,'drainage':None,'school_places':None},
            'limits':['No verified spare infrastructure capacity or legal buildability.',
                'WorldPop estimates are not parcel residents or a census; future years are projections.',
                'Footprints/heights/landcover are source estimates, not surveyed occupancy.',
                'Flood history/satellite/rainfall-threshold records are not flood probabilities or water-depth forecasts.',
                'Road reference land prices are not market prices, confirmed frontage or compensation.']}


def analyze_area(session,args):
    region=selection(session)
    year=int(args.get('population_year') or datetime.now(timezone.utc).year)
    if not 2010<=year<=2040:
        raise ValueError('Population year outside supported bounded range')
    day=int(args.get('traffic_weekday') or 2)
    hour=int(args['traffic_hour']) if args.get('traffic_hour') is not None else 18
    if not 1<=day<=7 or not 0<=hour<=23:raise ValueError('Invalid traffic weekday/hour')
    start=repository.instant(args['start_date']) if args.get('start_date') else None
    end=repository.instant(args['end_date']) if args.get('end_date') else None
    if start and end and start>=end:raise ValueError('Start date must precede end date')
    report=profile(region,year,True,day,hour,start,end)
    report.update(id=uuid4().hex,title=session.get('analysis_area',{}).get('title','Current plan/map area'),model_version=SCHEMA_VERSION)
    session.setdefault('area_reports',{})[report['id']]=report
    session['area_reports']=dict(list(session['area_reports'].items())[-6:])
    return report


def search_candidates(session,args):
    session.pop('query_features',None)
    body=Search(**{k:v for k,v in args.items() if k in Search.model_fields})
    region=bounds(body.bbox) if body.bbox else selection(session)
    if metric_area(region)>600_000_000:
        raise ValueError('Reduce the candidate search area to 600 km²')
    if not warehouse_configured():
        raise ValueError('Source parcel warehouse is unavailable; no candidate geometry was invented')
    with connect_to_warehouse() as c:
        c.execute('SET LOCAL statement_timeout=10000')
        table='plot' if c.execute("SELECT to_regclass('parcels.plot')").fetchone()[0] else 'land_plot'
        rows=c.execute('''WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) geom)
          SELECT p.id,ST_AsGeoJSON(p.geom),ST_Area(p.geom::geography),p.mdsdd
          FROM parcels.'''+table+''' p,a WHERE p.geom && a.geom AND ST_Intersects(p.geom,a.geom)
          AND ST_Area(p.geom::geography) BETWEEN %s AND %s AND (%s OR p.mdsdd=ANY(%s))
          ORDER BY ST_Area(p.geom::geography),p.id LIMIT %s''',
          (json.dumps(mapping(region)),body.minimum_area_m2,body.maximum_area_m2,not body.land_use_codes,body.land_use_codes,body.limit+1)).fetchall()
    features=[{'type':'Feature','id':str(i),'geometry':json.loads(g),'properties':{'parcel_id':str(i),'area_m2':a,'land_use':use,'land_use_label':parcels.land_use(use).get('label')}} for i,g,a,use in rows[:body.limit]]
    street=session.get('analysis_area',{}).get('target_street_geometry')
    if street and not body.bbox:
        forward,_=projection(shape(street));metric_street=transform(forward,shape(street))
        for feature in features:
            point=transform(forward,shape(feature['geometry'])).representative_point()
            feature['properties']['distance_to_requested_street_m']=round(point.distance(metric_street),1)
    session['candidate_features']=features
    session['last_search_ids']=[str(f['id']) for f in features]
    session['map_actions'].append({'type':'focus','bbox':list(region.bounds)})
    return {'candidates':features,'has_more':len(rows)>body.limit,'source':f'Team parcels.{table}',
            'search_extent':list(region.bounds),'selection_method':'Bounded first sample ordered by area then source ID; not best sites across the city',
            'vacancy_and_legal_permission':'unknown','next':'Evaluate selected IDs using candidate_compare before discussing tradeoffs'}


METRICS={
    'area_m2':('area_m2',),
    'population_density':('population','density_people_km2'),
    'road_distance_m':('roads','nearest_mapped_road_m'),
    'mapped_footprint_m2':('buildings','mapped_footprint_m2'),
    'transit_coverage_percent':('transit','coverage_percent'),
    'mapped_green_m2':('ground_cover','mapped_green_m2'),
    **{category+'_'+metric:('accessibility',category,key) for category in ('hospital','park','supermarket')
       for metric,key in [('travel_seconds','duration_s'),('route_m','distance_m')]},
}


class Criterion(Strict):
    metric: str
    direction: str
    weight: float=Field(gt=0,le=100)
    threshold: float | None=None

    @model_validator(mode='after')
    def valid(self):
        if self.metric not in METRICS or self.direction not in ('minimize','maximize'):
            raise ValueError('Unsupported metric/direction; use observable metrics only')
        return self


def metric_value(report,key):
    current=report
    for field in METRICS[key]:
        current=current.get(field) if isinstance(current,dict) else None
    return current if isinstance(current,(float,int)) and math.isfinite(current) else None


def rank_reports(reports,criteria):
    common=[c for c in criteria if all(metric_value(r,c.metric) is not None for r in reports)]
    rows=[]
    for report in reports:
        contributions=[];pending=[];failed=[]
        for c in criteria:
            value=metric_value(report,c.metric)
            if value is None:
                pending.append(c.metric)
            if c.threshold is not None and value is not None:
                if c.direction=='maximize' and value<c.threshold or c.direction=='minimize' and value>c.threshold:
                    failed.append(c.metric)
        for c in common:
            values=[metric_value(r,c.metric) for r in reports];lo,hi=min(values),max(values)
            score=50 if hi==lo else 100*(metric_value(report,c.metric)-lo)/(hi-lo)
            if c.direction=='minimize' and hi!=lo:
                score=100-score
            contributions.append({'metric':c.metric,'value':metric_value(report,c.metric),'score':round(score,2),'weight':c.weight})
        score=sum(c['score']*c['weight'] for c in contributions)/sum(c['weight'] for c in contributions) if contributions else None
        rows.append({'parcel_id':report['parcel_id'],'score':round(score,2) if score is not None else None,
                     'contributions':contributions,'missing_metrics':pending,'failed_thresholds':failed,
                     'qualification':'fails_declared_proxy_threshold' if failed else 'pending_missing_data' if pending else 'passes_declared_proxy_thresholds_only',
                     'legal_approval':'unknown','vacancy':'unknown'})
    rows.sort(key=lambda r:(bool(r['failed_thresholds']),r['score'] is None,-(r['score'] or 0),r['parcel_id']))
    for i,row in enumerate(rows):
        row['priority_order']=i+1 if row['score'] is not None and len(common)>=2 else None
    return {'rows':rows,'common_scored_metrics':[c.metric for c in common],
            'excluded_from_all_scores':[c.metric for c in criteria if c not in common],
            'ranking_status':'screening_priority' if len(common)>=2 else 'insufficient_common_criteria',
            'method':'Weighted min/max normalization across evaluated candidates, using only metrics known for EVERY candidate. Equal values get 50. Scores are relative priorities, not suitability probabilities. Missing criteria do not get zero or a bonus.'}


def compare(session,args):
    ids=args['parcel_ids']
    if not 2<=len(ids)<=6 or len(set(ids))!=len(ids):
        raise ValueError('Compare 2..6 unique source parcels')
    raw=json.loads(args['criteria_json'])
    if not isinstance(raw,list) or not 1<=len(raw)<=6:
        raise ValueError('Declare 1..6 weighted observable criteria')
    criteria=[Criterion(**c) for c in raw]
    if len({c.metric for c in criteria})!=len(criteria):
        raise ValueError('Each criterion may appear once')
    year=int(args.get('population_year') or datetime.now(timezone.utc).year)
    route_categories=list(dict.fromkeys(c.metric.split('_')[0] for c in criteria if c.metric.endswith(('_travel_seconds','_route_m'))))
    accessibility=None
    if route_categories:
        if not args.get('travel_mode'):raise ValueError('Choose car/bike/truck for route-based comparison; do not infer walking or motorcycle mode')
        from .accessibility import build
        accessibility=build(session,[parcel(i) for i in ids],route_categories,args['travel_mode'])
        route_rows={r['parcel_id']:r['amenities'] for r in accessibility['rows']}
    reports=[];features=[]
    for identifier in ids:
        source=parcel(identifier);region=shape(source['geometry'])
        report=profile(region,year,False)
        report.update(parcel_id=str(identifier),land_use=parcels.land_use(source.get('land_use')))
        if accessibility:report['accessibility']=route_rows[str(identifier)]
        reports.append(report)
        features.append({'type':'Feature','id':str(identifier),'geometry':source['geometry'],'properties':{'parcel_id':str(identifier),'area_m2':report['area_m2']}})
    assessment={'id':uuid4().hex,'created_at':now(),'criteria':[c.model_dump() for c in criteria],
                'accessibility_id':accessibility['id'] if accessibility else None,
                'reports':reports,**rank_reports(reports,criteria),
                'unresolved':['Verified zoning/land rights','Vacancy and actual demolition requirements','Utility spare capacity','School enrollment/age-specific demand','Flood probability/depth','Calibrated live traffic']}
    session.setdefault('assessments',{})[assessment['id']]=assessment
    session['assessments']=dict(list(session['assessments'].items())[-4:])
    session['candidate_features']=features
    return assessment


class ComparisonProgram(Strict):
    use: str
    floors: int=Field(ge=1,le=100)
    floor_area_m2: float=Field(ge=100,le=100000)
    floor_height_m: float=Field(default=3.2,gt=0,le=10)
    residents: int | None=Field(default=None,ge=0,le=20000)
    housing_units: int | None=Field(default=None,ge=0,le=10000)
    staff: int | None=Field(default=None,ge=0,le=20000)
    daily_users: int | None=Field(default=None,ge=0,le=20000)
    service_capacity: int | None=Field(default=None,ge=0,le=50000)
    setback_m: float=Field(default=5,ge=0,le=50)

    @model_validator(mode='after')
    def meaningful(self):
        if self.use not in ('residential','school','office','hospital'):
            raise ValueError('Use residential, school, office or hospital')
        if self.use=='residential' and (self.residents is None or self.housing_units is None):
            raise ValueError('Declare residents and apartment units for the common residential program')
        if self.use!='residential' and (self.staff is None or self.daily_users is None):
            raise ValueError('Declare staff and daily users for the common non-residential program')
        if self.use in ('school','hospital') and not self.service_capacity:
            raise ValueError('Declare proposed school places or hospital service capacity; this is not existing spare capacity')
        return self


def fitted_building(source,program):
    region=shape(source['geometry'])
    forward,backward=projection(region)
    site=transform(forward,region).buffer(-program.setback_m)
    if site.is_empty:
        raise ValueError(f'Parcel {source["id"]}: no space after proposed setback')
    parts=list(site.geoms) if site.geom_type=='MultiPolygon' else [site]
    half=math.sqrt(program.floor_area_m2/program.floors)/2
    for part in sorted(parts,key=lambda p:-p.area):
        center=polylabel(part,tolerance=1)
        square=box(center.x-half,center.y-half,center.x+half,center.y+half)
        for angle in range(0,180,15):
            candidate=rotate(square,angle,origin=(center.x,center.y))
            if part.covers(candidate):
                return {'name':f'Common {program.use} program','use':program.use,'footprint':mapping(transform(backward,candidate)),
                        'floors':program.floors,'height_m':program.floors*program.floor_height_m,
                        'gross_floor_area_m2':program.floor_area_m2,'residents':program.residents or 0,'units':program.housing_units or 0,
                        'staff':program.staff or 0,'daily_users':program.daily_users or 0,'service_capacity':program.service_capacity or 0}
    raise ValueError(f'Parcel {source["id"]}: the unchanged program does not fit the preliminary square footprint/setback test. Do not silently shrink it; choose another site or draw a custom design.')


def build_study(sources,program,mode,rainfall):
    from app.services.zoning.simulation import polygon
    region=box(*unary_union([shape(s['geometry']) for s in sources]).bounds).buffer(.0001)
    projects=[]
    for i,source in enumerate(sources):
        geometry=polygon(source['geometry'],'Candidate parcel').model_dump()
        site=shape(geometry)
        building=fitted_building(source,program)
        document=simulation_context.available_document(site)
        existing,ground=simulation_context.surfaces(geometry,[],document)
        proposal,_=simulation_context.surfaces(geometry,[building],document)
        projects.append({'id':f'site_{i}','title':f'Parcel {source["id"]}','site':geometry,
            'baseline':existing,'baseline_kind':'estimated','baseline_occupancy':'unknown',
            'baseline_source':'Mapped ground cover plus labelled unclassified-ground assumptions. Building inventory/occupancy not supplied; no vacancy inference.',
            'development':proposal,'utility_zone_id':'unknown'})
    network_id=None;network_doc=None
    if mode=='native':
        network_id,network_doc=simulation_context.acquire_network(region,750)
    prior=simulation_context.traffic_prior()
    return PlanningStudy(**{'title':f'Equal-program {program.use} candidate comparison','mode':'site_selection',
        'study_area':mapping(region),'planning_catalog':'qcvn_urban_2021','comparison_policy':'equal_program',
        'program_targets':{'floor_area_m2':program.floor_area_m2,'residents':program.residents or 0,'housing_units':program.housing_units or 0,'service_capacity':program.service_capacity or 0},
        'conditions':{'rainfall_mm':rainfall},'projects':projects,
        'options':[{'id':p['id'],'title':p['title'],'active_project_ids':[p['id']]} for p in projects],
        'utility_zones':[{'id':'unknown','source_kind':'unknown','source':'No verified network spare capacity or background load'}],
        'background_residents':0,'background_vehicles_hour':prior.cars[18]+prior.motorcycles[18],'traffic_prior':prior.model_dump(mode='json'),
        'traffic_network_mode':'osm_snapshot' if network_id else 'synthetic_corridor','traffic_snapshot_id':network_id,
        'source_note':'Agent multi-site study. Same declared building program across source parcels. Preliminary fitted square footprint, not optimized design. Existing occupancy/building inventory and utility capacity unknown; no empty-land/legal assertion. Ground cover uses installed source or labelled fallback. Native shares a local OSM network/background; different entrances remain scenario assumptions.',
        'development_context':{'inventory':{'status':'unknown','source':'No existing-building inventory integrated in this comparison; no vacancy inference'},
            'capacity':{'status':'unknown','source':'No verified spare network capacity'},
            'traffic':{'status':prior.source_kind,'source':prior.source,'background_vehicles_hour':prior.cars[18]+prior.motorcycles[18],
                'network':'osm_local' if network_id else 'prepared_on_detailed_run','snapshot_id':network_id,'radius_m':750,
                'network_source':network_doc.get('source') if network_doc else None},
            'same_declared_program':program.model_dump(),'source_parcel_ids':[str(s['id']) for s in sources]}})


def prepare_study(session,args):
    if args.get('selection')=='first_search':
        take=int(args.get('take') or 2)
        if not 1<=take<=3:raise ValueError('Select 1..3 candidates')
        ids=session.get('last_search_ids',[])[:take]
        if len(ids)!=take:raise ValueError('Not enough candidates in the latest search')
    else:
        ids=args['parcel_ids']
    if not 1<=len(ids)<=3 or len(set(ids))!=len(ids):
        raise ValueError('Choose 1..3 unique source parcels per bounded comparison study')
    program=ComparisonProgram(**json.loads(args['program_json']))
    sources=[parcel(i) for i in ids]
    study=build_study(sources,program,'screening',float(args.get('rainfall_mm',60)))
    ready=preflight(study)
    identifier=uuid4().hex
    session.setdefault('general_studies',{})[identifier]={'program':program.model_dump(),'parcel_ids':ids,'inputs':canonical_input(study),
        'created_at':now(),'context_hash':ready['context_hash'],'rainfall_mm':study.conditions.rainfall_mm}
    return {'study_id':identifier,'program':program.model_dump(),'parcel_ids':ids,'preflight':ready,
            'next':'Prepared only. Ask/choose screening or authorized native start. Geometry is a labelled preliminary placement; existing inventory is unknown.'}


def start_study(session,args,allow_native):
    mode=args['mode'];identifier=args['study_id']
    if mode not in ('screening','native') or mode=='native' and not allow_native:
        raise ValueError('Detailed mode requires UI opt-in; choose screening otherwise')
    prepared=session.get('general_studies',{}).get(identifier)
    if prepared is None:
        raise ValueError('Study not owned by this assistant session')
    existing=session.setdefault('general_runs',{})
    for job_id,meta in existing.items():
        if meta['general_study_id']==identifier and meta['mode']==mode:
            return {'job':runs.get_job(job_id),'reused':True}
    if len(existing)+len(session.get('development_runs',{}))>=12:
        raise ValueError('Session solver budget reached')
    if mode=='native':
        inputs=deepcopy(prepared['inputs'])
        network_id,network_doc=simulation_context.acquire_network(shape(inputs['study_area']),750)
        inputs.update(traffic_network_mode='osm_snapshot',traffic_snapshot_id=network_id)
        inputs['development_context']['traffic'].update(network='osm_local',snapshot_id=network_id,
            network_source=network_doc.get('source'),captured_at=network_doc.get('captured_at'))
        study=PlanningStudy(**inputs)
    else:
        study=PlanningStudy(**prepared['inputs'])
    ready=preflight(study)
    if ready['native_work_estimate']['sumo_runs']>24 and mode=='native':
        raise ValueError('Detailed workload exceeds 24 SUMO runs; reduce candidate count')
    saved,job=runs.start_study(canonical_input(study),ready['context_hash'],'urban-agent:'+session['id'],mode,'urban-'+identifier+'-'+mode)
    existing[job['id']]={'general_study_id':identifier,'kind':'urban_comparison','plan_id':None,'scenario_id':None,'revision':None,
        'mode':mode,'parcel_ids':prepared['parcel_ids'],'program':prepared['program']}
    return {'job':job,'study_id':saved['id'],'note':'Queued asynchronously. Compare completed results; do not infer benefit from a pending job.'}


def read_results(session,args):
    from .tools import compact_result
    ids=args.get('job_ids') or list(session.get('general_runs',{}))[-2:]
    if not ids or len(ids)>6 or not set(ids)<=session.get('general_runs',{}).keys():
        raise ValueError('Read only owned urban comparison jobs')
    rows=[]
    for identifier in ids:
        task=runs.get_job(identifier)
        row={'job_id':identifier,'status':task['status'],'captured':session['general_runs'][identifier],'error':task.get('error')}
        if task['status']=='succeeded' and task.get('result_id'):
            doc=runs.load_document(task['result_id'],'run')
            row['results']=compact_result(doc)
            row['results']['sources']=doc.get('context',{}).get('development_context')
        rows.append(row)
    return {'jobs':rows,'limits':'Compare identical program and captured model conditions. Missing baseline/capacity stays unknown; incomplete SUMO trip populations prevent a delay-only improvement conclusion.'}


def review(session):
    from .development_tools import current
    plan,scenario=current(session)
    from app.services.zoning.indicators import report
    output={'plan_id':plan['id'],'revision':plan['revision'],'scenario_id':scenario['id'],
            'zoning':report(plan,scenario['id'],None),'building_checks':[],
            'legal_status':'not_established','purpose':'Screen consistency with user-proposed limits and source availability; not legal approval'}
    ids=list(dict.fromkeys(b['parcel_id'] for b in scenario.get('buildings',[])))[:6]
    from app.routers.zoning import parcel_development_report
    for identifier in ids:
        value=safe(lambda:parcel_development_report(plan['id'],identifier,scenario['id']))
        output['building_checks'].append({'parcel_id':identifier,'report':value,'status':'available' if value else 'unknown'})
    return output


def report_bundle(session):
    result={'title':'Urban planning evidence summary','created_at':now(),'scope':session.get('analysis_area'),
            'areas':[{k:v for k,v in r.items() if k!='geometry'} for r in session.get('area_reports',{}).values()],
            'assessments':[{k:a.get(k) for k in ('id','criteria','rows','common_scored_metrics','excluded_from_all_scores','ranking_status','method','unresolved')} for a in session.get('assessments',{}).values()],
            'structured_queries':session.get('structured_queries',[]),
            'accessibility_results':list(session.get('accessibility_results',{}).values()),'displayed_route':session.get('route_result'),
            'development_jobs':session.get('development_runs',{}),'urban_jobs':session.get('general_runs',{}),
            'next_steps':['Resolve unknown data/rights/capacity before any real planning approval.','Use matched building programs for comparisons.','Read completed jobs; do not substitute queued state for outputs.']}
    result['simulation_outputs']=[]
    for identifier,meta in list({**result['development_jobs'],**result['urban_jobs']}.items())[-6:]:
        task=runs.get_job(identifier)
        captured={'job_id':identifier,'status':task['status'] if task else 'unavailable','captured':meta,'options':[]}
        if task and task['status']=='succeeded' and task.get('result_id'):
            doc=runs.load_document(task['result_id'],'run')
            captured.update(run_id=doc['id'],model_version=doc['model_version'],sources=doc.get('context',{}).get('development_context'))
            for option in doc.get('options',[]):
                rows=deepcopy(option.get('comparison',[])+option.get('traffic_comparison',[])+option.get('drainage_comparison',[]))
                for row in rows:
                    if row.get('after') is None:
                        row['proposal_estimate']=option['state']['metrics'].get(row['metric'])
                captured['options'].append({'id':option['id'],'rows':rows})
        result['simulation_outputs'].append(captured)
    lines=['# Urban planning evidence report','',f'Generated: {result["created_at"]}','',
           'Scope: '+str((result['scope'] or {}).get('title','Current workspace')),'']
    for query in result['structured_queries']:
        lines += ['## Filtered dataset query '+query['id'],'',
                  f"- Dataset: {query['query']['layer']}; matches in bounded fetch: {query['matched_in_bounded_fetch']}; unknown-filter rows: {query['unknown_filter_rows']}; source truncated: {query['source_truncated']}.",
                  '', '```json', json.dumps({k:query[k] for k in ('query','sources','rows','aggregates')},ensure_ascii=False,indent=2,default=str), '```','',
                  *['- '+note for note in query['interpretation']], '']
    for access in result['accessibility_results']:
        lines += ['## Travel accessibility '+access['id'],'',
                  'Provider: '+access['source']+'; vehicle: '+access['vehicle']+'; status: '+access['routing_status'],'',
                  '```json',json.dumps({'rows':access['rows'],'shortlist':access['shortlist'],'poi_evidence':access['poi_evidence']},ensure_ascii=False,indent=2,default=str),'```','',
                  *['- '+note for note in access['limitations']],'']
    if result['displayed_route']:
        lines += ['## Displayed route','','```json',json.dumps(result['displayed_route'],ensure_ascii=False,indent=2,default=str),'```','']
    for area in result['areas']:
        p=area['population']
        lines += ['## '+str(area['title']),'',f'- WorldPop {p["year"]}: {p["estimated_people"] if p["estimated_people"] is not None else "Unknown"} modelled people; raster coverage {p["coverage_percent"]}%.',
                  '- Mapped building source: '+str(area['buildings'].get('source','Unknown')),
                  '- Road context source: '+str(area['roads'].get('source','Unknown')),
                  '- Spare water, electricity, drainage and school capacity: Unknown.','']
        for name,value in area['layers'].items():
            lines.append(f'- {name}: {value["status"]}; {value["matching_count_in_bounded_fetch"]} matches in a bounded fetch (limit {value["query_limit"]}). No matches is not evidence of no hazard.')
        lines += ['',*['- '+v for v in area['limits']],'']
    for assessment in result['assessments']:
        lines += ['## Candidate comparison '+assessment['id'],'',assessment['method'],'',
                  '| Parcel | Relative score | Declared proxy qualification | Missing metrics |','|---|---:|---|---|']
        for row in assessment['rows']:
            lines.append(f'| {row["parcel_id"]} | {row["score"] if row["priority_order"] is not None else "Not ranked"} | {row["qualification"]} | {", ".join(row["missing_metrics"])} |')
        lines += ['', 'Criteria: '+json.dumps(assessment['criteria'],ensure_ascii=False),
                  'Unresolved: '+', '.join(assessment['unresolved']),'']
    lines += ['## Runs','', 'Development: '+', '.join(result['development_jobs']), 'Site studies: '+', '.join(result['urban_jobs']),
              '', 'Run IDs alone do not prove completion. Read completed solver outputs before interpreting impacts.','',
              '## Next steps','',*['- '+v for v in result['next_steps']]]
    for output in result['simulation_outputs']:
        lines += ['', '## Simulation '+output['job_id'],'','Status: '+output['status'],
            'Unknown is not zero. Proposal estimates are not net change when baseline is unknown. Native outputs remain assumption-based.','']
        for option in output['options']:
            lines += ['### '+option['id'],'','| Metric | Before | After / proposal estimate | Change | Unit | Comparability |','|---|---:|---:|---:|---|---|']
            for row in option['rows']:
                incomplete=row.get('comparability')=='not_comparable' or row.get('trip_population_complete') is False and row['metric'].endswith('delay_seconds')
                def fmt(value):return 'Unknown' if value is None else f'{value:.2f}' if isinstance(value,(int,float)) else str(value)
                after=row.get('after') if row.get('after') is not None else row.get('proposal_estimate')
                delta='Not comparable' if incomplete else fmt(row.get('delta'))
                label=row['metric']+(f' · {row["hour_local"]}:00 · seed {row.get("seed")}' if row.get('hour_local') is not None else '')
                lines.append(f'| {label} | {fmt(row.get("before"))} | {fmt(after)} | {delta} | {row.get("unit","")} | {row.get("comparability","")} |')
        if output.get('sources'):
            lines += ['', 'Captured source context:', '', '```json',json.dumps(output['sources'],ensure_ascii=False,indent=2),'```','']
    for query in session.get('dataset_queries',[]):
        lines += ['', '## Dataset: '+query['layer'],'',query['interpretation'],'',
                  '```json',json.dumps(query,ensure_ascii=False,default=str,indent=2),'```']
    if session.get('amenity_search'):
        lines += ['', '## Amenity site search','',session['amenity_search']['distance_method'],'',
                  '```json',json.dumps(session['amenity_search'],ensure_ascii=False,default=str,indent=2),'```']
    result['markdown']='\n'.join(lines)
    return result


def execute(name,args,session,allow_native):
    if name in ('accessibility_compare','route_show'):
        from . import accessibility
        return (accessibility.compare if name=='accessibility_compare' else accessibility.show_route)(session,args)
    if name in ('dataset_describe','dataset_query','dataset_query_refine'):
        from . import dataset_query
        return {'dataset_describe':dataset_query.describe,'dataset_query':dataset_query.run,
                'dataset_query_refine':dataset_query.refine}[name](session,args)
    if name in ('layer_query','amenity_site_search'):
        from . import layer_tools
        result=getattr(layer_tools,name)(session,args)
        if name=='amenity_site_search':session.pop('query_features',None)
        return result
    if name=='platform_overview':
        return {'capabilities':['Area Q&A without a plan','Named place/viewport/parcel analysis','PostGIS filters/joins/counts before display limits','Goong V2 named places, route access and route display','Explicit analysis boundary and selected web-place context','Multi-criteria candidate search and comparison','Plan consistency review','Equal-program residential/school/office/hospital site studies','Development edits and shared simulation','Evidence reporting'],
                'data_domains':['WorldPop population','Parcel land use','Overture mapped footprints','OSM road proximity','Historical congestion','Flood history/satellite/risk','Reference land prices','Rain stations','Installed services/transit/landcover'],
                'unknown':['Vacancy/land rights','Authoritative site-specific planning limits','Spare utility capacity','Actual school seats','Calibrated live traffic','Validated 2D flood depth'],
                'workflow':'Select area -> analyze -> search -> compare declared proxy criteria -> ask missing building program -> prepare equal-program study -> start -> read completed results -> explain tradeoffs/report'}
    if name=='area_select':return choose_area(session,args)
    if name=='area_analyze':return analyze_area(session,args)
    if name=='candidate_search':return search_candidates(session,args)
    if name=='candidate_compare':
        result=compare(session,args)
        session.pop('query_features',None)
        return result
    if name=='planning_review':return review(session)
    if name=='candidate_study_prepare':return prepare_study(session,args)
    if name=='candidate_study_start':return start_study(session,args,allow_native)
    if name=='urban_results':return read_results(session,args)
    if name=='urban_report':return report_bundle(session)
    raise ValueError('Unknown urban tool')
