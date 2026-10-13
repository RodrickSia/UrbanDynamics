from shapely.geometry import box, mapping
import pytest
from src.pipelines.land_price.automatic_fill import build


def fixture():
    rows = [dict(id=str(i), road=name, ward='Fixture', region_id='test',
                 **{'from': 'A', 'to': 'B'}, pdf_page=1,
                 residential_1000_vnd_m2=100 + i, commercial_1000_vnd_m2=60,
                 other_nonagricultural_1000_vnd_m2=50)
            for i, name in enumerate(['Alpha', 'Missing street'])]
    source = dict(records=rows, published_unit='1000 VND/m2', source_url='https://example.test/table.pdf')
    roads = {'elements': [dict(type='way', id=i, tags={'name': name},
             geometry=[{'lon': 106.1, 'lat': 10.1 + i / 100}, {'lon': 106.2, 'lat': 10.1 + i / 100}])
             for i, name in enumerate(['Alpha', 'Other'], 1)]}
    wards = {'features': [dict(type='Feature', geometry=mapping(box(106, 10, 107, 11)),
                              properties=dict(name='Fixture', osm_relation_id=1))]}
    return source, roads, wards


def test_missing_names_are_allocated_and_every_road_gets_a_source_price():
    source, roads, wards = fixture()
    rows, coverage = build(source, roads, wards, box(106, 10, 107, 11), {'features': []})
    assert {f['id'] for f in rows['features']} == {'0', '1'}
    assert {f['id'] for f in coverage['features']} == {'osm:1', 'osm:2'}
    actual = {tuple((p['lon'], p['lat']) for p in w['geometry']) for w in roads['elements']}
    for feature in rows['features'] + coverage['features']:
        assert tuple(map(tuple, feature['geometry']['coordinates'])) in actual
        assert feature['properties']['geometry_reviewed'] is False
        reference = next(r for r in source['records'] if r['id'] == feature['properties']['price_record_id'])
        assert feature['properties']['residential_vnd_m2'] == reference['residential_1000_vnd_m2'] * 1000


def test_existing_segment_is_preserved_and_invalid_prices_are_rejected():
    source, roads, wards = fixture()
    old = {'type': 'Feature', 'id': '0', 'geometry': {'type': 'LineString', 'coordinates': [[106.11,10.11],[106.12,10.11]]},
           'properties': dict(residential_vnd_m2=100000, commercial_vnd_m2=60000, other_nonagricultural_vnd_m2=50000)}
    matches, _ = build(source, roads, wards, box(106, 10, 107, 11), {'features': [old]})
    assert matches['features'][0] == old
    source['records'][1]['residential_1000_vnd_m2'] = -1
    with pytest.raises(ValueError, match='positive integers'):
        build(source, roads, wards, box(106, 10, 107, 11), {'features': []})


def test_wards_without_pdf_rows_use_nearest_priced_ward():
    source, roads, wards = fixture()
    wards['features'].append(dict(type='Feature', geometry=mapping(box(107,10,108,11)),
                                 properties=dict(name='Unpriced ward', osm_relation_id=2)))
    roads['elements'].append(dict(type='way',id=3,tags={'name':'Outside table'},
        geometry=[{'lon':107.1,'lat':10.2},{'lon':107.2,'lat':10.2}]))
    _, coverage = build(source, roads, wards, box(106,10,108,11), {'features':[]})
    feature = next(f for f in coverage['features'] if f['id']=='osm:3')
    assert feature['properties']['match_method']=='nearest_ward_table_reference'
    assert feature['properties']['residential_vnd_m2'] > 0
