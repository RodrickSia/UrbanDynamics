"""Bounded route-based screening of real parcels and sourced POIs."""
from uuid import uuid4

from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

from app.services import goong_places
from app.services.simulation.integrated.context import projection
from . import layer_tools


def poi_source(session,region,radius):
    snapshot=session.get('map_pois') or {}
    mapped=layer_tools.system_amenities(snapshot)
    try:
        value=layer_tools.load_pois(region,radius)
    except ValueError:
        if not mapped:raise
        value={'features':[],'source':'System map POIs only; supplement unavailable',
               'coverage':snapshot.get('coverage'),'attribution':'System basemap provider'}
    return mapped+value['features'],{k:v for k,v in value.items() if k!='features'}


def build(session,features,categories,vehicle,radius=2000,pois=None,evidence=None,objective='duration'):
    if not 1<=len(features)<=6 or not categories or any(c not in layer_tools.CATEGORIES for c in categories):
        raise ValueError('Accessibility accepts 1..6 parcels and supermarket/park/hospital categories')
    if vehicle not in goong_places.VEHICLES or not 50<=radius<=5000:
        raise ValueError('Choose car/bike/truck and a 50..5000m POI discovery radius; bike retains the provider mode label, walking/motorcycle are unsupported')
    region=unary_union([shape(f['geometry']) for f in features]).envelope
    if pois is None:pois,evidence=poi_source(session,region,radius)
    forward,_=projection(region)
    origins=[list(shape(f['geometry']).representative_point().coords)[0] for f in features]
    projected_origins=[transform(forward,shape(f['geometry'])).representative_point() for f in features]
    grouped={category:[] for category in categories}
    seen=set()
    for poi in pois:
        category=poi.get('properties',{}).get('category')
        if category not in grouped or layer_tools.poi_conflict(poi):continue
        geometry=shape(poi['geometry']);point=geometry.representative_point()
        signature=(str(poi.get('id')),category,point.x,point.y)
        if signature in seen:continue
        seen.add(signature)
        grouped[category].append((poi,transform(forward,point),[point.x,point.y]))
    destinations=[];destination_indices={};eligible=[]
    for origin in projected_origins:
        choices={}
        for category in categories:
            nearest=sorted(grouped[category],key=lambda p:(origin.distance(p[1]),str(p[0].get('id'))))
            picks=[p for p in nearest if origin.distance(p[1])<=radius][:2]
            indices=[]
            for poi,point,coordinate in picks:
                key=(str(poi.get('id')),category,*coordinate)
                if key not in destination_indices:
                    destination_indices[key]=len(destinations)
                    destinations.append({'feature':poi,'coordinate':coordinate,'category':category})
                indices.append(destination_indices[key])
            choices[category]=indices
        eligible.append(choices)
    matrices=[[] for _ in origins];errors=[]
    for start in range(0,len(destinations),12):
        batch=destinations[start:start+12]
        try:
            response=goong_places.matrix(origins,[d['coordinate'] for d in batch],vehicle)
            for index,row in enumerate(response['rows']):matrices[index].extend(row)
        except ValueError as error:
            errors.append(str(error))
            for row in matrices:row.extend([{'status':'unavailable','distance_m':None,'duration_s':None} for _ in batch])
    rows=[]
    for index,feature in enumerate(features):
        amenities={}
        for category in categories:
            candidates=[(matrices[index][j],destinations[j]) for j in eligible[index][category]
                        if matrices[index][j]['status']=='OK']
            chosen=min(candidates,key=lambda item:(item[0]['distance_m'],item[0]['duration_s']) if objective=='distance' else (item[0]['duration_s'],item[0]['distance_m'])) if candidates else None
            cell,destination=chosen if chosen else ({'distance_m':None,'duration_s':None},None)
            properties=destination['feature']['properties'] if destination else {}
            amenities[category]={**cell,'name':(properties.get('name') or 'Unnamed mapped '+category) if destination else None,'poi_id':str(destination['feature'].get('id')) if destination else None,
                'destination':destination['coordinate'] if destination else None,'poi_source':properties.get('poi_source','OpenStreetMap') if destination else None,
                'selection':('Shortest route' if objective=='distance' else 'Fastest route')+' among up to two nearby mapped facilities, not all facilities',
                'status':'available' if chosen else 'unknown_no_valid_route_or_mapped_facility'}
        rows.append({'parcel_id':str(feature['id']),'origin':list(origins[index]),'amenities':amenities})
    result={'id':uuid4().hex,'vehicle':vehicle,'discovery_radius_m':radius,'rows':rows,
            'source':'Goong Distance Matrix V2','poi_evidence':evidence,
            'routing_status':'partial_or_unavailable' if errors else 'completed' if destinations else 'no_mapped_destinations',
            'errors':errors,'pairs_requested':len(origins)*len(destinations),
            'shortlist':{'parcels':len(features),'facilities_per_category_per_parcel':2,'destination_points':len(destinations)},
            'limitations':['Route estimates between representative parcel/POI points; actual entrances and access are not verified.',
                'Finite mapped POI coverage; shortlist is not an exhaustive accessibility optimum.',
                'Provider duration is not an observed journey, live congestion guarantee or before/after SUMO result.',
                'Unknown/unreachable destinations remain unknown, never zero travel time.']}
    session.setdefault('accessibility_results',{})[result['id']]=result
    session['accessibility_results']=dict(list(session['accessibility_results'].items())[-4:])
    return result


def compare(session,args):
    from .general_tools import parcel
    ids=args['parcel_ids']
    if not 1<=len(ids)<=6 or len(set(ids))!=len(ids):raise ValueError('Choose 1..6 unique source parcels')
    features=[parcel(identifier) for identifier in ids]
    return build(session,features,args['categories'],args['travel_mode'],args.get('radius_m') or 2000)


def show_route(session,args):
    result=session.get('accessibility_results',{}).get(args['accessibility_id'])
    if not result:raise ValueError('Choose an owned saved accessibility result')
    row=next((r for r in result['rows'] if r['parcel_id']==str(args['parcel_id'])),None)
    amenity=row['amenities'].get(args['category']) if row else None
    if not amenity or not amenity.get('destination'):raise ValueError('No sourced destination/valid matrix route is available for this parcel/category')
    route=goong_places.directions(row['origin'],amenity['destination'],result['vehicle'])
    route.update(id=uuid4().hex,parcel_id=row['parcel_id'],category=args['category'],destination_name=amenity['name'] or 'Unnamed mapped '+args['category'],accessibility_id=result['id'])
    feature={'type':'Feature','id':route['id'],'geometry':route['geometry'],
             'properties':{k:v for k,v in route.items() if k!='geometry'}}
    session['route_features']={'type':'FeatureCollection','features':[feature]}
    session['route_result']={k:v for k,v in route.items() if k!='geometry'}
    session['map_actions'].append({'type':'focus','bbox':list(shape(route['geometry']).bounds)})
    return route
