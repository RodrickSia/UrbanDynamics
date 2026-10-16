import pytest
from shapely.geometry import box,Point,mapping
from app.services.agent import accessibility as a
from app.services import goong_places


def feature(identifier,geometry,**properties):
    return {'type':'Feature','id':identifier,'geometry':mapping(geometry),'properties':properties}


def test_routes_choose_shortest_for_distance_and_fastest_for_time(monkeypatch):
    parcels=[feature('1',box(106.7,10.8,106.7001,10.8001))]
    pois=[feature('h1',Point(106.701,10.8),category='hospital',name='Hospital A'),
          feature('h2',Point(106.702,10.8),category='hospital',name='Hospital B')]
    monkeypatch.setattr(goong_places,'matrix',lambda *args:{'rows':[[{'status':'OK','distance_m':2000,'duration_s':100},
                                                                   {'status':'OK','distance_m':1000,'duration_s':200}]]})
    distance=a.build({},parcels,['hospital'],'car',2000,pois,{},objective='distance')
    time=a.build({},parcels,['hospital'],'car',2000,pois,{})
    assert distance['rows'][0]['amenities']['hospital']['name']=='Hospital B'
    assert time['rows'][0]['amenities']['hospital']['name']=='Hospital A'


def test_provider_failure_stays_unknown_and_does_not_create_a_route(monkeypatch):
    def fail(*args):raise ValueError('Provider unavailable')
    monkeypatch.setattr(goong_places,'matrix',fail)
    session={'map_actions':[]}
    result=a.build(session,[feature('1',box(106.7,10.8,106.7001,10.8001))],['hospital'],'car',2000,
                   [feature('h1',Point(106.701,10.8),category='hospital',name='Hospital')],{})
    assert result['rows'][0]['amenities']['hospital']['duration_s'] is None
    with pytest.raises(ValueError):a.show_route(session,{'accessibility_id':result['id'],'parcel_id':'1','category':'hospital'})
    assert 'route_features' not in session


def test_route_ownership_and_real_polyline(monkeypatch):
    session={'map_actions':[],'accessibility_results':{'owned':{'id':'owned','vehicle':'car','rows':[
        {'parcel_id':'1','origin':[106.7,10.8],'amenities':{'park':{'name':'Park','destination':[106.71,10.81]}}}]}}}
    with pytest.raises(ValueError):a.show_route(session,{'accessibility_id':'other','parcel_id':'1','category':'park'})
    monkeypatch.setattr(goong_places,'directions',lambda *args:{'geometry':{'type':'LineString','coordinates':[[106.7,10.8],[106.71,10.81]]},'source':'Goong test','distance_m':1000,'duration_s':120})
    result=a.show_route(session,{'accessibility_id':'owned','parcel_id':'1','category':'park'})
    assert result['distance_m']==1000
    assert session['route_features']['features'][0]['geometry']['type']=='LineString'


def test_standard_polyline_decode_and_invalid_modes():
    assert goong_places.decode_polyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@')[0]==[-120.2,38.5]
    with pytest.raises(ValueError):goong_places.matrix([[106.7,10.8]],[[106.71,10.81]],'walking')
