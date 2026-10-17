"""Bounded dataset lookup and sourced amenity proximity, independent of map visibility."""
import hashlib
import json
import os
import math
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import Point, Polygon, box, mapping, shape
from shapely.ops import transform

from app import repository
from app.services import parcels
from app.services.simulation.integrated.context import projection
from app.services.zoning.geometry import projected
from src.shared.database import connect_to_warehouse, warehouse_configured
from .scope import metric_area

POI_LOCK = threading.Lock()
CATEGORIES = {'supermarket': ('shop', 'supermarket'), 'park': ('leisure', 'park'),
              'hospital': ('amenity', 'hospital')}


def validate_map_pois(value):
    from .models import Search
    if not isinstance(value,dict) or value.get('type')!='FeatureCollection':
        raise ValueError('Invalid map POI snapshot')
    Search(bbox=value.get('bbox'))
    if not value.get('bbox') or not isinstance(value.get('features'),list) or len(value['features'])>1500:
        raise ValueError('Map POI snapshot must have a valid extent and at most 1500 points')
    features=[]
    for feature in value['features']:
        geometry=feature.get('geometry',{})
        coordinates=geometry.get('coordinates',[])
        if geometry.get('type')!='Point' or len(coordinates)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in coordinates):
            raise ValueError('Map POIs must be finite WGS84 points')
        if not -180<=coordinates[0]<=180 or not -85<=coordinates[1]<=85:
            raise ValueError('Invalid map POI coordinate')
        properties={str(k)[:80]:v[:240] if isinstance(v,str) else v for k,v in list(feature.get('properties',{}).items())[:30]
                    if isinstance(v,(str,int,float,bool)) and (not isinstance(v,float) or math.isfinite(v))}
        features.append({'type':'Feature','id':str(feature.get('id',''))[:300],
                         'geometry':geometry,'properties':properties})
    return {'type':'FeatureCollection','features':features,'bbox':value['bbox'],
            'captured_at':str(value.get('captured_at',''))[:80],
            'source':'System Points of Interest — loaded basemap vector tiles',
            'coverage':'Loaded viewport tiles only; zoom-dependent and not an exhaustive POI database'}


def system_amenities(snapshot):
    features=[]
    for feature in (snapshot or {}).get('features',[]):
        properties=feature['properties']
        count=properties.get('point_count',1)
        if properties.get('clustered') is True or isinstance(count,(int,float)) and count>1:
            continue  # Cluster label coordinates are not individual facility locations.
        # Categorize only explicit provider category/type tags, never guess a
        # hospital or supermarket from a business name alone.
        category=next((c for c,(k,v) in CATEGORIES.items() if properties.get(k)==v),None)
        tags=' '.join(str(v).lower().replace('_',' ') for k,v in properties.items()
                      if k.lower() in ('class','subclass','type','category','category_name','icon','maki'))
        if not category:
            category=next((c for c in CATEGORIES if re.search(r'\b'+c+r'\b',tags)),None)
        if category:
            features.append({**feature,'id':'system/'+str(feature.get('id','')),
                             'properties':{**properties,'category':category,'poi_source':'System Points of Interest'}})
    return features


def poi_conflict(feature):
    properties=feature.get('properties',{})
    category=properties.get('category')
    name=str(properties.get('name','')).casefold()
    # Preserve raw source tags, but do not qualify an explicit pet shop or health
    # station as the requested supermarket/hospital just because a source tag is wrong.
    if category=='supermarket' and any(t in name for t in ('thú cưng','pet shop','petshop','vật nuôi')):
        return 'Mapped supermarket tag conflicts with explicit pet-shop name'
    if category=='hospital' and 'bệnh viện' not in name and any(t in name for t in ('trạm y tế','phòng khám','clinic','nha khoa')):
        return 'Mapped hospital tag conflicts with clinic/health-station name'
    if category=='park' and any(t in name for t in ('bãi đỗ xe','parking lot','car park')):
        return 'Mapped park tag conflicts with parking name'
    return None


def buffered(region, radius):
    forward, inverse = projection(region)
    return transform(inverse, transform(forward, region).buffer(radius)) if radius else region


def layer_query(session, args):
    from .general_tools import selection, parcel
    layer = args['layer']
    special={'population','traffic','sumo_network','sumo_simulation','poi'}
    if layer not in repository.LAYER_INFO and layer not in special:
        raise ValueError('Unknown dataset layer; read source_catalog for installed source IDs')
    radius = float(args.get('radius_m') or 0)
    if not 0 <= radius <= 5000:
        raise ValueError('Dataset radius must be between 0 and 5000 m')
    region = shape(parcel(str(args['parcel_id']))['geometry']) if args.get('parcel_id') else selection(session)
    extent = buffered(region, radius)
    if metric_area(extent) > 650_000_000:
        raise ValueError('Narrow the dataset query area to 650 km² including the buffer')
    temporal = repository.LAYER_INFO.get(layer,{}).get('time_enabled', False)
    try:
        if layer in special:
            result=special_dataset(layer,region,extent,args,session)
        else:
            result = repository.features(layer, list(extent.bounds),
                                         args.get('start_date') if temporal else None,
                                         args.get('end_date') if temporal else None, limit=2000)
    except repository.LayerUnavailable:
        raise ValueError('Dataset '+layer+' is not loaded/available in the connected data service; no replacement data was invented') from None
    forward, _ = projection(region)
    metric_region = transform(forward, region)
    text = (args.get('text') or '').casefold().strip()
    records = []
    for feature in result.get('features', []):
        if not feature.get('geometry'):
            continue
        geometry = shape(feature['geometry'])
        distance = metric_region.distance(transform(forward, geometry))
        properties = feature.get('properties', {})
        if distance > radius + .1 or (text and text not in json.dumps(properties, ensure_ascii=False).casefold()):
            continue
        record={'id':feature.get('id'), 'distance_m':round(distance, 1), 'properties':properties}
        if layer=='land_price':
            unreviewed=properties.get('geometry_reviewed') is False or properties.get('source_values_reviewed') is False
            record['quality']='Unreviewed reference allocation; not a verified price for this road/parcel' if unreviewed else 'Source reference; verify applicability'
            record['source_road_differs']=bool(properties.get('source_road') and properties.get('road') and
                properties['source_road'].casefold()!=properties['road'].casefold())
        records.append(record)
    records.sort(key=lambda row:(row['distance_m'], str(row['id'])))
    value = {'layer':layer, 'title':repository.LAYER_INFO.get(layer,{}).get('title', layer),
             'source':'Connected map dataset API / team warehouse', 'metadata':result.get('metadata'),
             'status':result.get('status') or ('records_found' if records else 'no_matching_records'),
             'records':records[:20], 'matching_count_in_bounded_fetch':len(records),
             'query_limit':2000, 'radius_m':radius, 'search_extent':list(extent.bounds),
             'date_filter_supported':temporal,
             'interpretation':('Published road-segment reference price, not market price, parcel frontage assignment, purchase cost or compensation. Preserve unit, effective date and geometry review/match confidence.'
                               if layer=='land_price' else 'Source records only; missing records do not establish absence of hazard or complete coverage.')}
    session.setdefault('dataset_queries', []).append(value)
    session['dataset_queries'] = session['dataset_queries'][-6:]
    return value


def special_dataset(layer,region,extent,args,session):
    from datetime import time as clock_time
    from uuid import UUID
    from app.routers import traffic,traffic_sumo
    bbox=','.join(str(v) for v in extent.bounds)
    weekday=int(args.get('traffic_weekday') or 2);hour=int(args.get('traffic_hour') if args.get('traffic_hour') is not None else 18)
    if not 1<=weekday<=7 or not 0<=hour<=23:raise ValueError('Invalid traffic weekday/hour')
    if layer=='population':
        from app.services.area_indicators import sources
        year=int(args.get('population_year') or 2026)
        if not 2010<=year<=2040:raise ValueError('Population year must be 2010..2040')
        value=sources.population(mapping(region),year)
        coverage=min(100,float(value['covered_m2'])/metric_area(region)*100) if value else None
        properties={'population_year':year,'estimated_people':float(value['value']) if value and coverage>=99 else None,
                    'partial_sum_people':float(value['value']) if value else None,'coverage_percent':coverage,
                    'unit':'modeled people','interpretation':'WorldPop model, not census; total unknown below 99% coverage'}
        return {'features':[{'type':'Feature','id':'population-'+str(year),'geometry':mapping(region),'properties':properties}],
                'metadata':{'source':'WorldPop raster in team warehouse','year':year,'details':value}}
    if layer=='traffic':return traffic.traffic_prediction(bbox=bbox,limit=2000,weekday=weekday,period=clock_time(hour))
    if layer=='sumo_network':return traffic.sumo_network(bbox=bbox,limit=2000)
    if layer=='sumo_simulation':
        if args.get('run_id'):return traffic_sumo.get_run_features(UUID(str(args['run_id'])))
        from app.services import traffic_sumo_prediction
        cached=traffic_sumo_prediction.cached_scenario(weekday,f'{hour:02d}:00')
        if cached:
            result=traffic_sumo.get_run_features(UUID(cached['run_id']))
            result.setdefault('metadata',{}).update({'source_run_id':cached['run_id'],'weekday':weekday,'hour':hour,'existing_cache':True})
            return result
        with connect_to_warehouse() as connection:
            rows=connection.execute('''SELECT run_id,weekday,period FROM transport.sumo_congestion_scenario_cache
                ORDER BY weekday,period LIMIT 20''').fetchall()
        return {'features':[],'status':'not_precomputed_for_requested_period',
                'metadata':{'source':'Existing system SUMO scenario catalog','catalog':traffic_sumo.simulation_catalog(),
                'requested_weekday':weekday,'requested_hour':hour,
                'available_runs':[{'run_id':str(i),'weekday':d,'period':str(t)} for i,d,t in rows],
                'next':'Choose an existing run_id/period to read saved features. Querying never starts a new simulation.'}}
    snapshot=session.get('map_pois')
    if snapshot and snapshot.get('features'):
        return {'features':snapshot['features'],'metadata':{k:v for k,v in snapshot.items() if k!='features'}}
    pois=load_pois(region,0)
    return {'features':pois['features'],'metadata':{k:v for k,v in pois.items() if k!='features'}}


def parse_pois(document):
    """Keep actual OSM names/tags and geometry; do not substitute clinics for hospitals."""
    features = []
    for item in document.get('elements', []):
        tags = item.get('tags', {})
        category = next((c for c,(k,v) in CATEGORIES.items() if tags.get(k)==v), None)
        if not category:
            continue
        coords = [(p['lon'],p['lat']) for p in item.get('geometry', []) if 'lon' in p and 'lat' in p]
        center = item.get('center', item)
        geometry = None
        if len(coords)>=4 and coords[0]==coords[-1]:
            candidate = Polygon(coords)
            if candidate.is_valid:
                geometry = candidate
        if geometry is None and 'lon' in center and 'lat' in center:
            geometry = Point(center['lon'],center['lat'])
        if geometry is not None:
            features.append({'type':'Feature','id':f"{item.get('type')}/{item.get('id')}",
                             'geometry':mapping(geometry), 'properties':{**tags,'category':category}})
    return features


def load_pois(region, radius):
    extent = buffered(region, radius)
    west,south,east,north = [round(v,5) for v in extent.bounds]
    envelope = box(west,south,east,north)
    if metric_area(envelope) > 80_000_000:
        raise ValueError('Amenity query exceeds 80 km²; zoom into a neighborhood or choose a smaller radius')
    root = Path(os.getenv('AGENT_SQLITE_PATH', '.runtime/agent.sqlite')).parent / 'agent-pois'
    root.mkdir(parents=True,exist_ok=True)
    offline = Path(os.getenv('AGENT_POI_SNAPSHOT',str(root/'offline-bbbike-saigon.json')))
    if offline.is_file():
        try:
            document = json.loads(offline.read_text(encoding='utf-8'))
            if document.get('schema_version')==1 and shape(document['coverage_geometry']).covers(envelope):
                features = [f for f in document['features'] if shape(f['geometry']).intersects(envelope)]
                return {**{k:v for k,v in document.items() if k not in ('features','coverage_geometry')},
                        'features':features,'cache_hit':True,'query_bbox':[west,south,east,north]}
        except (OSError,ValueError,KeyError,TypeError):
            pass
    key = hashlib.sha256(json.dumps([west,south,east,north,'amenities-v1']).encode()).hexdigest()
    # The bundled offline snapshot may live on a read-only or NAS-backed
    # runtime volume. Keep writable Overpass cache files in the container's
    # app-owned temporary directory instead of requiring chown on that mount.
    cache_root = Path(os.getenv('AGENT_POI_CACHE_DIR', '/tmp/urbandynamics-agent-pois-cache'))
    cache_root.mkdir(parents=True,exist_ok=True)
    cache = cache_root / (key+'.json')
    with POI_LOCK:
        if cache.is_file():
            try:
                cached = json.loads(cache.read_text(encoding='utf-8'))
                age = datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(cached['captured_at']).timestamp()
                if 0 <= age < 86400:
                    return {**cached,'cache_hit':True}
            except (ValueError,KeyError,OSError):
                pass
        # One bounded request, all three categories; no citywide scraping.
        query = ('[out:json][timeout:20];('+''.join(
            f'nwr["{k}"="{v}"]({south},{west},{north},{east});' for k,v in CATEGORIES.values())+');out center;')
        errors = []
        for endpoint in (os.getenv('AGENT_OVERPASS_URL','https://overpass-api.de/api/interpreter'),
                         'https://overpass.private.coffee/api/interpreter'):
            try:
                response = requests.post(endpoint,data={'data':query},
                    headers={'User-Agent':'UrbanDynamics/2026 (https://github.com/RodrickSia/UrbanDynamics)'},timeout=(5,25))
                response.raise_for_status()
                if len(response.content)>8_000_000:
                    raise ValueError('Amenity response exceeds 8 MB')
                data = response.json()
                if data.get('remark') or 'elements' not in data:
                    raise ValueError('Incomplete Overpass result')
                value = {'source':'OpenStreetMap via Overpass', 'endpoint':endpoint,
                         'attribution':'© OpenStreetMap contributors', 'captured_at':datetime.now(timezone.utc).isoformat(),
                         'bbox':[west,south,east,north], 'cache_hit':False,'features':parse_pois(data),
                         'coverage':'Mapped POIs only; completeness/opening status not verified'}
                temporary = cache.with_suffix('.tmp')
                temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
                temporary.replace(cache)
                return value
            except (requests.RequestException,ValueError) as error:
                errors.append(type(error).__name__)
        raise ValueError('OSM amenity data unavailable; no amenities or distances were invented. Retry later or configure AGENT_OVERPASS_URL. '+', '.join(errors))


def parcel_pool(region, minimum, maximum):
    if not warehouse_configured():
        raise ValueError('Parcel warehouse unavailable; source parcels were not invented')
    with connect_to_warehouse() as connection:
        connection.execute('SET LOCAL statement_timeout=10000')
        table = 'plot' if connection.execute("SELECT to_regclass('parcels.plot')").fetchone()[0] else 'land_plot'
        rows = connection.execute('''WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) geom)
          SELECT p.id,ST_AsGeoJSON(p.geom),ST_Area(p.geom::geography),p.mdsdd
          FROM parcels.'''+table+''' p,a WHERE p.geom && a.geom AND ST_Intersects(p.geom,a.geom)
          AND ST_Area(p.geom::geography) BETWEEN %s AND %s
          ORDER BY ST_Area(p.geom::geography),p.id LIMIT 251''',
          (json.dumps(mapping(region)),minimum,maximum)).fetchall()
    return [{'type':'Feature','id':str(i),'geometry':json.loads(g),
             'properties':{'parcel_id':str(i),'area_m2':float(a),'land_use':use,
                           'land_use_label':parcels.land_use(use).get('label')}} for i,g,a,use in rows[:250]],len(rows)>250


def proximity_candidates(features, pois, requirements, limit):
    if not features:
        return [],[]
    region = shape(features[0]['geometry'])
    forward,_ = projection(region)
    groups = {category:[(f,transform(forward,shape(f['geometry']))) for f in pois
                        if f['properties']['category']==category and not poi_conflict(f)] for category in requirements}
    rows = []
    for feature in features:
        # Representative point avoids measuring a large parcel's remote edge as an entrance.
        point = transform(forward,shape(feature['geometry'])).representative_point()
        evidence = {}
        for category, radius in requirements.items():
            pairs = [(point.distance(g), f) for f,g in groups[category]]
            nearest = min(pairs,key=lambda pair:pair[0]) if pairs else None
            evidence[category] = {'distance_m':round(nearest[0],1) if nearest else None,
                'name':nearest[1]['properties'].get('name','Unnamed mapped '+category) if nearest else None,
                'source':nearest[1]['properties'].get('poi_source','OpenStreetMap') if nearest else None,
                'osm_id':nearest[1]['id'] if nearest else None, 'maximum_distance_m':radius,
                'meets_proximity':nearest is not None and nearest[0]<=radius}
        meets = all(v['meets_proximity'] for v in evidence.values())
        # Unknown is never scored as zero distance.
        score = sum(v['distance_m']/requirements[k] if v['distance_m'] is not None else 1e6 for k,v in evidence.items())
        rows.append({'feature':feature,'amenities':evidence,'meets_all':meets,'distance_score':score})
    rows.sort(key=lambda row:(not row['meets_all'],row['distance_score'],str(row['feature']['id'])))
    return rows[:limit],rows


def amenity_site_search(session,args):
    from .general_tools import selection, bounds
    region = bounds(args['bbox']) if args.get('bbox') else selection(session)
    minimum = float(args.get('minimum_area_m2') if args.get('minimum_area_m2') is not None else 40)
    maximum = float(args.get('maximum_area_m2') if args.get('maximum_area_m2') is not None else 1000)
    if not 1<=minimum<=maximum<=100000:
        raise ValueError('Invalid parcel area interval')
    requirements = json.loads(args['requirements_json'])
    if not isinstance(requirements,dict) or not requirements or any(k not in CATEGORIES for k in requirements):
        raise ValueError('Requirements must map supermarket/park/hospital to maximum straight-line meters')
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not 50<=v<=5000 for v in requirements.values()):
        raise ValueError('Proximity radii must be 50..5000 m')
    limit = int(args.get('limit',3))
    people = args.get('household_people')
    if not 1<=limit<=6 or (people is not None and not 1<=people<=100):
        raise ValueError('Invalid result limit or household size')
    # A representative point can be inside the area or just outside a crossing parcel.
    features,truncated = parcel_pool(region,minimum,maximum)
    if not features:
        raise ValueError('No source parcels match this area/size interval; broaden the area or size, not fabricated geometry')
    from shapely.ops import unary_union
    query_region = unary_union([shape(f['geometry']) for f in features]).envelope
    system_snapshot=session.get('map_pois')
    mapped=system_amenities(system_snapshot)
    try:
        source = load_pois(query_region,max(requirements.values()))
    except ValueError:
        if not mapped:raise
        source={'features':[],'source':'System Points of Interest only — supplemental provider unavailable',
                'attribution':'System basemap provider POIs','captured_at':system_snapshot.get('captured_at'),
                'coverage':'Loaded viewport POIs only; missing/outside-view POIs remain unknown'}
    if mapped:
        source={**source,'features':mapped+source['features'],'supplemental_source':source['source'],
                'source':'System Points of Interest + '+source['source'],
                'attribution':'System basemap POIs; '+source.get('attribution','OpenStreetMap contributors'),
                'system_poi_count':len(mapped),'system_poi_extent':system_snapshot.get('bbox'),
                'system_poi_coverage':system_snapshot.get('coverage')}
    selected,all_rows = proximity_candidates(features,source['features'],requirements,limit)
    travel_mode=args.get('travel_mode')
    routed=None
    if travel_mode:
        from .accessibility import build
        routed=build(session,[r['feature'] for r in selected],list(requirements),travel_mode,
                     max(requirements.values()),source['features'],{k:v for k,v in source.items() if k!='features'},objective='distance')
        lookup={r['parcel_id']:r for r in routed['rows']}
        for row in selected:
            route_row=lookup[str(row['feature']['id'])]
            for category,previous in row['amenities'].items():
                route=route_row['amenities'][category]
                row['amenities'][category]={**previous,**route,'straight_line_distance_m':previous['distance_m'],
                    'maximum_distance_m':requirements[category],
                    'meets_proximity':route['distance_m'] is not None and route['distance_m']<=requirements[category]}
            row['meets_all']=all(a['meets_proximity'] for a in row['amenities'].values())
            row['distance_score']=sum(a['distance_m']/requirements[c] if a['distance_m'] is not None else 1e6 for c,a in row['amenities'].items())
        selected.sort(key=lambda r:(not r['meets_all'],r['distance_score'],str(r['feature']['id'])))
    matched = [row for row in selected if row['meets_all']]
    # Keep nearest partial alternatives visible, but explicitly fail unfulfilled requirements.
    session['candidate_features'] = [{**row['feature'],'properties':{
        **row['feature']['properties'],'amenity_match':row['meets_all']}} for row in selected]
    session['last_search_ids'] = [f['id'] for f in session['candidate_features']]
    session['map_actions'].append({'type':'focus','bbox':list(query_region.bounds)})
    result = {'source_parcels':'Team parcel warehouse','amenity_source':{k:v for k,v in source.items() if k!='features'},
        'excluded_category_conflicts':[{'id':f.get('id'),'name':f['properties'].get('name'),
            'reason':poi_conflict(f)} for f in source['features'] if poi_conflict(f)][:20],
        'requirements_m':requirements,'household_people':people,'parcel_area_interval_m2':[minimum,maximum],
        'area_interval_is_screening_default':args.get('minimum_area_m2') is None or args.get('maximum_area_m2') is None,
        'status':'matching_candidates' if matched else 'no_all_criteria_match_in_sample',
        'sample_size':len(features),'sample_truncated':truncated,'matching_in_sample':sum(row['meets_all'] for row in (selected if routed else all_rows)),
        'matching_count_scope':'Route-evaluated shortlist only' if routed else 'Straight-line parcel sample',
        'accessibility_id':routed['id'] if routed else None,'travel_mode':travel_mode,'route_shortlist_size':len(selected) if routed else 0,
        'results':[{'parcel_id':r['feature']['id'],**r['feature']['properties'],
                    'meets_all_proximity_requirements':r['meets_all'],'amenities':r['amenities']} for r in selected],
        'method':'Bounded sample of up to 250 parcels ordered by area/ID, ranked by sum of normalized amenity distances. Not exhaustive citywide optimization.',
        'distance_method':('Goong Distance Matrix V2 route distance for vehicle='+travel_mode+'; bounded shortlist and unverified entrances.' if routed else 'Straight-line from an interior parcel point to mapped POI geometry (provider centers when only a point is available); not walking route, entrance or travel time.'),
        'unresolved':['Vacancy/ownership','Residential permission and setbacks','Budget and market price',
                      'Building floor area/floors for the household','Actual entrances and pedestrian access'],
        'note':'Household size is project context, not proof of an adequate parcel or permitted house. If size/budget are absent, disclose screening defaults and ask for refinement.'}
    session['amenity_search'] = result
    return result
