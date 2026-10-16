"""Fixed Goong Places endpoints; the REST credential never reaches the browser."""
import math
import os
import threading
import time
from copy import deepcopy

import requests

LOCK = threading.Lock()
CACHE = {}
ENDPOINTS={'AutoComplete':'/v2/place/autocomplete','Detail':'/v2/place/detail',
           'DistanceMatrix':'/v2/distancematrix','Directions':'/v2/direction'}
VEHICLES={'car','bike','truck'}


def request(endpoint, params):
    key = os.getenv('GOONG_REST_API_KEY', '').strip()
    if not key:
        raise ValueError('Goong place search is not configured on the backend')
    if endpoint not in ENDPOINTS:
        raise ValueError('Unsupported places operation')
    cache_key = (key, endpoint, tuple(sorted(params.items())))
    with LOCK:
        cached = CACHE.get(cache_key)
        if cached and time.monotonic()-cached[0] < 300:
            return deepcopy(cached[1])
    try:
        response = requests.get('https://rsapi.goong.io'+ENDPOINTS[endpoint],
                                params={**params,'api_key':key}, timeout=(5,12))
        if response.status_code != 200:
            raise ValueError(f'Goong place service returned HTTP {response.status_code}')
        value = response.json()
    except (requests.RequestException, requests.exceptions.JSONDecodeError):
        raise ValueError('Goong place service is temporarily unavailable') from None
    if not isinstance(value,dict) or (value.get('status') not in ('OK','ZERO_RESULTS',None)) or (value.get('status') is None and not any(k in value for k in ('rows','routes'))):
        raise ValueError('Goong could not resolve this place request')
    with LOCK:
        if len(CACHE) >= 128:
            CACHE.pop(next(iter(CACHE)))
        CACHE[cache_key] = (time.monotonic(),deepcopy(value))
    return value


def search(query):
    query = query.strip()
    if not 3 <= len(query) <= 160:
        raise ValueError('Enter 3–160 characters to search for a place')
    value = request('AutoComplete', {'input':query,'limit':5,'has_deprecated_administrative_unit':'true'})
    results = []
    for row in value.get('predictions',[])[:5]:
        if not row.get('place_id'):
            continue
        structured = row.get('structured_formatting') or {}
        results.append({'id':str(row['place_id']), 'name':structured.get('main_text') or row.get('description',''),
                        'context':structured.get('secondary_text') or row.get('description',''),
                        'previous_address':row.get('deprecated_description'),
                        'administrative_units':row.get('compound'),'previous_administrative_units':row.get('deprecated_compound')})
    return {'source':'Goong Places V2','results':results}


def detail(identifier):
    if not isinstance(identifier,str) or not 1 <= len(identifier) <= 2000:
        raise ValueError('Choose a valid Goong place identifier')
    row = request('Detail', {'place_id':identifier,'has_deprecated_administrative_unit':'true'}).get('result') or {}
    location = (row.get('geometry') or {}).get('location') or {}
    lat, lng = location.get('lat'), location.get('lng')
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (lat,lng)) or not -85<=lat<=85 or not -180<=lng<=180:
        raise ValueError('Goong returned no valid coordinates for this place')
    return {'id':identifier,'name':row.get('name') or row.get('formatted_address','Place'),
            'context':row.get('formatted_address',''), 'longitude':lng,'latitude':lat,
            'temperatureC':None,'weatherLabel':'Weather unavailable','source':'Goong Places V2',
            'previous_address':row.get('deprecated_description'),'administrative_units':row.get('compound'),
            'previous_administrative_units':row.get('deprecated_compound'),'precision':'Provider point, not administrative or parcel boundary'}


def coordinates(value):
    if not isinstance(value,(list,tuple)) or len(value)!=2:
        raise ValueError('Coordinates must be [longitude,latitude]')
    lng,lat=value
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value) or not -180<=lng<=180 or not -85<=lat<=85:
        raise ValueError('Invalid route coordinates')
    return f'{lat:.7f},{lng:.7f}'


def matrix(origins,destinations,vehicle):
    if vehicle not in VEHICLES:raise ValueError('Choose car, provider bike mode or truck; walking/motorcycle are not supported by the verified API enum')
    if not 1<=len(origins)<=6 or not 1<=len(destinations)<=12:
        raise ValueError('Matrix batches allow 1..6 origins and 1..12 destinations')
    value=request('DistanceMatrix',{'origins':'|'.join(coordinates(p) for p in origins),
        'destinations':'|'.join(coordinates(p) for p in destinations),'vehicle':vehicle})
    rows=value.get('rows',[])
    if len(rows)!=len(origins) or any(len(row.get('elements',[]))!=len(destinations) for row in rows):
        raise ValueError('Goong returned an incomplete matrix; no distance was invented')
    result=[]
    for row in rows:
        cells=[]
        for element in row['elements']:
            distance=(element.get('distance') or {}).get('value')
            duration=(element.get('duration') or {}).get('value')
            valid=element.get('status')=='OK' and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in (distance,duration))
            cells.append({'status':'OK' if valid else str(element.get('status') or 'unavailable'),
                          'distance_m':distance if valid else None,'duration_s':duration if valid else None})
        result.append(cells)
    return {'source':'Goong Distance Matrix V2','vehicle':vehicle,'rows':result,
            'interpretation':'Provider route estimate for representative points; not observed travel time, guaranteed entrance access or post-development traffic prediction'}


def decode_polyline(encoded):
    if not isinstance(encoded,str) or not 1<=len(encoded)<=100000:
        raise ValueError('Invalid route geometry')
    coordinates_out=[];index=0;lat=lng=0
    try:
        while index<len(encoded):
            pair=[]
            for _ in range(2):
                result=shift=0
                while True:
                    digit=ord(encoded[index])-63;index+=1
                    if not 0<=digit<=63 or shift>30:raise ValueError('Invalid polyline')
                    result|=(digit&31)<<shift;shift+=5
                    if digit<32:break
                pair.append(~(result>>1) if result&1 else result>>1)
            lat+=pair[0];lng+=pair[1]
            point=[lng/1e5,lat/1e5];coordinates(point);coordinates_out.append(point)
    except (IndexError,TypeError):raise ValueError('Incomplete route geometry') from None
    if len(coordinates_out)<2:raise ValueError('Route has no usable line')
    return coordinates_out


def directions(origin,destination,vehicle):
    if vehicle not in VEHICLES:raise ValueError('Unsupported route vehicle')
    value=request('Directions',{'origin':coordinates(origin),'destination':coordinates(destination),'vehicle':vehicle,'alternatives':'false'})
    routes=value.get('routes') or []
    if not routes:raise ValueError('No Goong route was returned; do not draw a straight-line replacement')
    route=routes[0]
    geometry={'type':'LineString','coordinates':decode_polyline((route.get('overview_polyline') or {}).get('points'))}
    legs=route.get('legs') or []
    def total(key):
        values=[(leg.get(key) or {}).get('value') for leg in legs]
        return sum(values) if values and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0 for v in values) else None
    return {'source':'Goong Directions V2','vehicle':vehicle,'geometry':geometry,
            'distance_m':total('distance'),'duration_s':total('duration'),
            'warnings':route.get('warnings',[]),'interpretation':'Provider route estimate; points may be snapped to roads and entrances are unverified. Not a simulation forecast.'}
