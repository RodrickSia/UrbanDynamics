import pytest
import importlib.util
from pathlib import Path
from shapely.geometry import GeometryCollection, Point, LineString, box, mapping, shape
from shapely.errors import GEOSException
from src.pipelines.land_price.road_matcher import match, clip_unique_path
from src.pipelines.land_price.road_sources import relation_polygon
from src.pipelines.land_price.transform import run as prices
from src.pipelines.land_price import pipeline, road_sources
from src.pipelines.land_price import road_matcher


def inputs():
    row = {'id':'one','region_id':'hcmc_previous','ward':'SÀI GÒN',
           'road':'ĐƯỜNG NGUYỄN VĂN A','from':'ĐƯỜNG B','to':'ĐƯỜNG C',
           'segment_scope':'between_endpoints','extraction_review_required':True,
           'residential_1000_vnd_m2':10000,'commercial_1000_vnd_m2':6000,
           'other_nonagricultural_1000_vnd_m2':5000}
    source = {'records':[row],'published_unit':'1000 VND/m2','source_url':'fixture',
              'effective_from':'2026-01-01'}
    ways = []
    for i,name,coords in [(1,'Nguyễn Văn A',[(106.701,10.805),(106.709,10.805)]),
                         (2,'B',[(106.703,10.803),(106.703,10.807)]),
                         (3,'C',[(106.707,10.803),(106.707,10.807)]),
                         (4,'Nguyễn Văn A',[(106.901,10.805),(106.909,10.805)])]:
        ways.append({'id':i,'tags':{'name':name},'geometry':[{'lon':x,'lat':y} for x,y in coords]})
    wards = {'features':[{'geometry':mapping(box(106.70,10.80,106.71,10.81)),
                          'properties':{'name':'Phường Sài Gòn','admin_level':'6','osm_relation_id':99}}]}
    return source,{'elements':ways},wards


def test_clips_to_crossroads_in_correct_ward_and_keeps_price_units():
    source,roads,wards = inputs()
    result,pending = match(source,roads,wards)
    assert not pending
    geometry = shape(result['features'][0]['geometry'])
    assert geometry.bounds[0] == pytest.approx(106.703,abs=1e-6)
    assert geometry.bounds[2] == pytest.approx(106.707,abs=1e-6)
    assert result['features'][0]['properties']['osm_way_ids'] == [1]
    published,_ = prices(source,result)
    assert published['features'][0]['properties']['residential_vnd_m2'] == 10_000_000
    assert published['features'][0]['properties']['match_confidence'] == 'spatially_checked'
    assert published['features'][0]['properties']['geometry_reviewed'] is False


def test_missing_or_ambiguous_ward_is_not_auto_published():
    source,roads,wards = inputs()
    assert match(source,roads,{'features':[]})[1][0]['unmatched_reason'] == 'current_ward_boundary_missing'
    wards['features'] *= 2
    assert match(source,roads,wards)[1][0]['unmatched_reason'] == 'ambiguous_ward_identity'


def test_old_level_8_ward_cannot_replace_current_commune():
    source,roads,wards = inputs()
    wards['features'][0]['properties']['admin_level'] = '8'
    assert not match(source,roads,wards)[0]['features']


def test_named_endpoint_without_intersection_is_pending():
    source,roads,wards = inputs()
    roads['elements'][2]['geometry'] = [{'lon':106.707,'lat':10.806},{'lon':106.707,'lat':10.807}]
    assert match(source,roads,wards)[1][0]['unmatched_reason'] == 'endpoint_not_intersecting'


def test_flyover_crossing_is_not_a_named_road_intersection():
    source, roads, wards = inputs()
    roads['elements'][1]['tags'].update(bridge='yes', layer='1')
    assert match(source, roads, wards)[1][0]['unmatched_reason'] == 'endpoint_not_intersecting'


def test_whole_road_is_clipped_to_ward():
    source,roads,wards = inputs()
    source['records'][0].update(segment_scope='whole_road', **{'from':'TRỌN ĐƯỜNG','to':'TRỌN ĐƯỜNG'})
    roads['elements'][0]['geometry'][0]['lon'] = 106.69
    result,pending = match(source,roads,wards)
    assert not pending
    assert shape(result['features'][0]['geometry']).bounds[0] == pytest.approx(106.70,abs=1e-6)


def test_disconnected_same_name_in_ward_is_not_one_whole_road():
    source,roads,wards = inputs()
    source['records'][0]['segment_scope'] = 'whole_road'
    roads['elements'][3]['geometry'] = [{'lon':106.701,'lat':10.809},{'lon':106.709,'lat':10.809}]
    assert match(source,roads,wards)[1][0]['unmatched_reason'] == 'disconnected_named_road'


def test_loop_has_two_paths_and_is_rejected():
    ring = LineString([(0,0),(100,0),(100,100),(0,100),(0,0)])
    with pytest.raises(ValueError,match='ambiguous_road_path'):
        clip_unique_path(ring,LineString([(50,-10),(50,10)]),LineString([(50,90),(50,110)]))


def test_branched_road_with_unique_path_keeps_only_between_endpoints():
    road = LineString([(0,0),(100,0),(200,0)]).union(LineString([(100,0),(100,100)]))
    result,_,_ = clip_unique_path(road,LineString([(50,-10),(50,10)]),LineString([(150,-10),(150,10)]))
    assert result.length == pytest.approx(100)


def test_boundary_hole_is_not_price_area_and_open_rings_fail():
    def member(coords,role):
        return {'type':'way','role':role,'geometry':[{'lon':x,'lat':y} for x,y in coords]}
    outer = [(0,0),(10,0),(10,10),(0,10),(0,0)]
    inner = [(2,2),(3,2),(3,3),(2,3),(2,2)]
    polygon = relation_polygon({'members':[member(outer,'outer'),member(inner,'inner')]})
    assert polygon.area == 99
    with pytest.raises(ValueError,match='rings are not closed'):
        relation_polygon({'members':[member(outer[:-1],'outer')]})


def test_nearby_same_name_roads_are_not_assumed_to_be_carriageways():
    road = LineString([(0,0),(200,0)]).union(LineString([(0,20),(200,20)]))
    a,b = LineString([(50,-10),(50,30)]),LineString([(150,-10),(150,30)])
    with pytest.raises(ValueError,match='multiple_road_corridors'):
        clip_unique_path(road,a,b)
    assert clip_unique_path(road,a,b,allow_dual=True)[0].length == pytest.approx(200)


def test_citywide_pipeline_drops_legacy_name_only_and_preserves_manual_override(monkeypatch, tmp_path):
    source, roads, wards = inputs()
    source['records'].append({**source['records'][0], 'id':'legacy', 'road':'Missing road'})
    automatic, _ = match({'records':[source['records'][0]]}, roads, wards)
    manual = automatic['features'][0]
    manual['properties'].update(reviewed=True, price_values_reviewed=True, auto_approved=False)
    legacy = {**manual, 'properties':{**manual['properties'], 'price_record_id':'legacy',
              'reviewed':False, 'auto_approved':True, 'match_method':'osm_exact_name'}}
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setattr(pipeline.extract, 'run', lambda *a, **k:(source, {}))
    monkeypatch.setattr(pipeline, 'read_json', lambda p:{'features':[manual, legacy]})
    monkeypatch.setattr(road_sources, 'prepare', lambda **k:(roads, wards))
    monkeypatch.setattr(pipeline.load, 'run', lambda document:document)
    result = pipeline.run(segments='fixture', full_city=True)
    assert len(result['features']) == 1
    assert result['features'][0]['properties']['geometry_reviewed'] is True
    assert result['metadata']['pending_rows'] == 1


def test_source_failure_does_not_publish_a_partial_snapshot(monkeypatch, tmp_path):
    source, _, _ = inputs()
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setattr(pipeline.extract, 'run', lambda *a, **k:(source, {}))
    def unavailable(**kwargs):
        raise RuntimeError('Source unavailable')
    monkeypatch.setattr(road_sources, 'prepare', unavailable)
    published = []
    monkeypatch.setattr(pipeline.load, 'run', lambda document:published.append(document))
    with pytest.raises(RuntimeError, match='Source unavailable'):
        pipeline.run(full_city=True)
    assert not published


def test_overloaded_road_query_subdivides_and_caches_complete_result(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    calls = []
    def source(query):
        calls.append(query)
        if len(calls) == 1:
            raise RuntimeError('Server overloaded')
        return {'elements':[{'id':1}], 'osm3s':{'timestamp_osm_base':'fixture-time'}}, 'https://fixture'
    monkeypatch.setattr(road_sources, 'request', source)
    result = road_sources.road_chunk((106,10,107,11), cached=True)
    assert result['elements'] == [{'id':1}]
    assert len(calls) == 5
    assert len(result['queries']) == 4
    assert result['source_endpoints'] == ['https://fixture']
    assert road_sources.road_chunk((106,10,107,11), cached=True) == result
    assert len(calls) == 5


def test_subdivision_failure_does_not_create_a_complete_chunk(monkeypatch, tmp_path):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    def unavailable(query):
        raise RuntimeError('Unavailable')
    monkeypatch.setattr(road_sources, 'request', unavailable)
    with pytest.raises(RuntimeError):
        road_sources.road_chunk((106,10,107,11), cached=True)
    assert not list(tmp_path.rglob('bbox-v1-*.json'))


def test_wards_only_cli_never_fetches_or_publishes_roads(monkeypatch, tmp_path, capsys):
    script = Path(__file__).resolve().parents[3]/'scripts/prepare-land-price-segments.py'
    spec = importlib.util.spec_from_file_location('prepare_land_price_segments', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, _, _ = inputs()
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setattr(module, 'extract', lambda *a, **k:(source, {}))
    calls = []
    def fetch_wards(boundary, cached):
        calls.append((boundary, cached))
        return {'features':[{}], 'metadata':{'license':'ODbL 1.0'}}
    def forbidden(*args, **kwargs):
        raise AssertionError('Wards-only mode must not fetch roads')
    monkeypatch.setattr(module, 'fetch_wards', fetch_wards)
    monkeypatch.setattr(module, 'prepare', forbidden)
    module.run(cached=True, wards_only=True)
    assert calls == [(tmp_path/'inputs/hcmc_expanded_boundary.geojson', True)]
    assert 'ward_boundary_count' in capsys.readouterr().out
    assert not (tmp_path/'review/land_price_auto_segments.geojson').exists()


def test_computed_point_collections_are_not_overlaid_twice():
    road = LineString([(0,0),(200,0)])
    start = GeometryCollection([Point(50,1e-10)])
    end = GeometryCollection([Point(150,1e-10)])
    result, _, _ = clip_unique_path(road,start,end,computed_intersections=True)
    assert result.length == pytest.approx(100)


def test_osm_overlay_failure_keeps_one_row_pending_without_losing_valid_rows(monkeypatch):
    source, roads, wards = inputs()
    source['records'].append({**source['records'][0], 'id':'second'})
    original = road_matcher.clip_unique_path
    calls = []
    def unstable(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise GEOSException('Unstable overlay')
        return original(*args, **kwargs)
    monkeypatch.setattr(road_matcher, 'clip_unique_path', unstable)
    result, pending = match(source, roads, wards)
    assert len(result['features']) == 1
    assert result['features'][0]['id'] == 'second'
    assert pending[0]['unmatched_reason'] == 'osm_geometry_overlay_error'


def test_published_segment_is_clipped_to_approved_city_scope_and_labelled_partial():
    source, roads, wards = inputs()
    city = box(106.70,10.80,106.705,10.81)
    result, pending = match(source,roads,wards,city_geometry=city)
    assert not pending
    feature = result['features'][0]
    assert city.covers(shape(feature['geometry']))
    assert feature['properties']['geometry_coverage'] == 'partial_city_clipped_segment'
    assert feature['properties']['source_segment_coverage'] == 'between_named_intersections_within_ward'
    assert feature['properties']['city_boundary_clipped'] is True


def test_segment_outside_approved_city_is_pending():
    source, roads, wards = inputs()
    result, pending = match(source,roads,wards,city_geometry=box(106.9,10.8,107,10.9))
    assert not result['features']
    assert pending[0]['unmatched_reason'] == 'outside_city_boundary'
