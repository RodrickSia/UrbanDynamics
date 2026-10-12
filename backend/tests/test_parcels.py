import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import parcels


def road(**changes):
    return {'feature_id': 'road-1', 'distance_m': 5, 'properties': {
        'road': 'Example road', 'match_confidence': 'spatially_checked',
        'residential_vnd_m2': 10_000_000,
        'geometry_coverage': 'between_named_intersections_within_ward',
        'source_url': 'https://example.org/source.pdf', **changes,
    }}


def test_unique_spatial_match_can_estimate_mapped_residential_area():
    result = parcels.price_reference({'uniq_id': 'known', 'mdsdd': 'ODT', 'area_m2': 100}, [road()])
    assert result['status'] == 'reference'
    assert result['unit_price_vnd_m2'] == 10_000_000
    assert result['estimated_land_total_vnd'] == 1_000_000_000
    assert result['method'] == 'nearby_road_geometry'
    assert result['price_category'] == 'Residential'
    assert result['normalized_land_use'] == 'Residential land'
    assert result['classification_confidence'] == 'high'


@pytest.mark.parametrize('source,category,field,family', [
    ('OTC', 'Residential', 'residential_vnd_m2', 'Residential land'),
    ('K.sạn', 'Commercial', 'commercial_vnd_m2', 'Hotel'),
    ('C.hang', 'Commercial', 'commercial_vnd_m2', 'Retail'),
    ('Xg.dầu', 'Commercial', 'commercial_vnd_m2', 'Fuel retail'),
    ('B.viện', 'Other non-agricultural', 'other_nonagricultural_vnd_m2', 'Hospital'),
    ('Tr.học', 'Other non-agricultural', 'other_nonagricultural_vnd_m2', 'School'),
    ('C.ty', 'Other non-agricultural', 'other_nonagricultural_vnd_m2', 'Company'),
])
def test_observed_codes_use_their_road_category_price(source, category, field, family):
    prices = {'residential_vnd_m2': 163_000_000, 'commercial_vnd_m2': 97_800_000,
              'other_nonagricultural_vnd_m2': 81_500_000}
    result = parcels.price_reference({'uniq_id': 'parcel', 'mdsdd': source, 'area_m2': 100},
                                     [road(**prices)])
    assert result['price_category'] == category
    assert result['normalized_land_use'] == family
    assert result['unit_price_vnd_m2'] == prices[field]
    assert result['estimated_land_total_vnd'] == 100 * prices[field]


@pytest.mark.parametrize('source', ['DSK', 'CDG', 'Khác', 'R/p', 'Kh.sách', 'Dầu khí',
                                    'Tr.tâm', 'TL', '12345', None])
def test_unclear_source_codes_keep_null_price(source):
    result = parcels.price_reference({'uniq_id': 'parcel', 'mdsdd': source, 'area_m2': 100},
                                     [road(commercial_vnd_m2=97_800_000)])
    assert result['price_category'] is None
    assert result['unit_price_vnd_m2'] is None
    assert result['estimated_land_total_vnd'] is None


def test_missing_matching_road_price_is_null_even_when_land_use_is_known():
    result = parcels.price_reference({'uniq_id': 'parcel', 'mdsdd': 'K.san', 'area_m2': 100},
                                     [road(commercial_vnd_m2=None)])
    assert result['price_category'] == 'Commercial'
    assert result['unit_price_vnd_m2'] is None
    assert result['estimated_land_total_vnd'] is None


def test_imperfect_source_variant_retains_family_with_low_confidence():
    result = parcels.price_reference({'uniq_id': 'parcel', 'mdsdd': 'B.viƯn', 'area_m2': 100},
                                     [road(other_nonagricultural_vnd_m2=81_500_000)])
    assert result['normalized_land_use'] == 'Hospital'
    assert result['classification_confidence'] == 'low'
    assert result['valuation_confidence'] == 'low'


@pytest.mark.parametrize('attributes,candidates,status', [
    ({'mdsdd': 'ODT', 'area_m2': 100}, [], 'unavailable'),
    ({'mdsdd': 'ODT', 'area_m2': 100}, [road(), {**road(road='Other road'), 'feature_id': '2'}], 'ambiguous'),
    ({'mdsdd': 'null', 'area_m2': 100}, [road()], 'unsupported_land_use'),
    ({'mdsdd': 'ODT', 'area_m2': 100}, [road(geometry_coverage='whole_named_road_proxy')], 'unverified'),
    ({'mdsdd': 'ODT', 'area_m2': 100, 'conflicting_land_use': True}, [road()], 'unsupported_land_use'),
])
def test_uncertain_associations_never_produce_a_total(attributes, candidates, status):
    result = parcels.price_reference(attributes, candidates)
    assert result['status'] == status
    assert result['estimated_land_total_vnd'] is None


def test_zero_or_nonfinite_prices_are_unavailable():
    for value in [0, -1, float('nan'), float('inf'), None]:
        result = parcels.price_reference({'mdsdd': 'ODT', 'area_m2': 100}, [road(residential_vnd_m2=value)])
        assert result['estimated_land_total_vnd'] is None


def test_same_road_different_segment_prices_remain_ambiguous():
    result = parcels.price_reference({'mdsdd': 'ODT', 'area_m2': 100},
                                     [road(), road(residential_vnd_m2=20_000_000)])
    assert result['status'] == 'ambiguous'


@pytest.mark.parametrize('road_distance_m', [5, 26])
def test_apartment_planning_gives_l_plot_only_a_low_confidence_unit_reference(road_distance_m):
    parcel = {'uniq_id': 'known', 'mdsdd': 'L', 'area_m2': 5893.07,
              'loai_dat_qh': 'Đất chung cư phức hợp: 5874.19 m2; Đất giao thông: 25.01 m2'}
    result = parcels.price_reference(parcel, [{**road(), 'distance_m': road_distance_m}])
    assert result['status'] == 'provisional'
    assert result['price_category'] == 'Residential'
    assert result['classification_basis'] == 'planning'
    assert result['classification_confidence'] == 'low'
    assert result['valuation_confidence'] == 'low'
    assert result['unit_price_vnd_m2'] == 10_000_000
    assert result['estimated_land_total_vnd'] is None
    assert parcels.price_reference(parcel, [])['unit_price_vnd_m2'] is None
    assert parcels.price_reference({**parcel, 'conflicting_land_use': True}, [road()])['unit_price_vnd_m2'] is None


def test_l_plot_without_clear_apartment_planning_keeps_null_price():
    for planning in (None, 'Đất giao thông: 25.01 m2', 'Đất chung cư phức hợp',
                     'Đất chung cư phức hợp: 5874.19 m2; Đất thương mại: 100 m2'):
        result = parcels.price_reference({'mdsdd': 'L', 'area_m2': 5893.07,
                                          'loai_dat_qh': planning}, [road()])
        assert result['unit_price_vnd_m2'] is None
        assert result['estimated_land_total_vnd'] is None


def test_opposite_side_road_price_is_provisional_only_when_unique_and_checked():
    parcel = {'uniq_id': 'known', 'mdsdd': 'ODT', 'area_m2': 100}
    result = parcels.price_reference(parcel, [{**road(), 'distance_m': 28}])
    assert result['status'] == 'provisional'
    assert result['unit_price_vnd_m2'] == 10_000_000
    assert result['estimated_land_total_vnd'] is None
    assert result['valuation_confidence'] == 'low'
    ambiguous = parcels.price_reference(parcel, [
        {**road(), 'distance_m': 28},
        {**road(road='Another road'), 'feature_id': 'road-2', 'distance_m': 32},
    ])
    assert ambiguous['status'] == 'ambiguous'
    assert ambiguous['unit_price_vnd_m2'] is None
    assert parcels.price_reference(parcel, [{**road(), 'distance_m': 41}])['unit_price_vnd_m2'] is None


def test_planning_breakdown_keeps_source_areas_without_fabricating_percentages():
    rows = parcels.planning_breakdown('Đất ở: 180.9 m2; Đất giao thông: 10.8 m2; Unknown')
    assert rows == [{'label': 'Đất ở', 'area_m2': 180.9}, {'label': 'Đất giao thông', 'area_m2': 10.8}]


def test_palette_uses_land_use_groups_and_normalizes_unknown():
    assert parcels.land_use('OTC')['color'] == '#D79B8C'
    assert parcels.land_use('OTC')['color_source'] == 'category_palette'
    assert parcels.land_use('Tr.học')['color'] == '#86A5C5'
    assert parcels.land_use('GT')['color'] == '#A8AFB9'
    assert parcels.land_use('DSK')['color'] == '#94a3b8'
    assert parcels.land_use('DSK')['color_source'] == 'unknown'
    assert parcels.land_use('null')['code'] is None
    assert parcels.land_use('unrecognized')['color'] == '#94a3b8'


def test_parcel_route_validates_id_and_has_safe_storage_errors(monkeypatch):
    client = TestClient(app)
    assert client.get('/api/v1/parcels/0').status_code == 422
    assert client.get('/api/v1/parcels/not-an-id').status_code == 422
    monkeypatch.setattr(parcels, 'detail', lambda _: None)
    assert client.get('/api/v1/parcels/1').status_code == 404
    def unavailable(_):
        raise OSError('private connection details')
    monkeypatch.setattr(parcels, 'detail', unavailable)
    response = client.get('/api/v1/parcels/1')
    assert response.status_code == 503
    assert 'private connection' not in response.text


@pytest.mark.skipif(os.getenv('POSTGIS_TESTS') != '1', reason='Requires isolated PostGIS test database')
def test_canonical_geometry_tile_colors_and_price_api(monkeypatch):
    import uuid
    import mercantile
    import mapbox_vector_tile
    from psycopg.types.json import Jsonb
    from src.shared.database import connect_to_warehouse

    # All fixture writes and view refreshes roll back, including on test failure.
    connection = connect_to_warehouse()
    key = 'parcel-test-' + uuid.uuid4().hex
    @contextmanager
    def same_transaction():
        yield connection
    monkeypatch.setattr(parcels, 'connect_to_warehouse', same_transaction)
    try:
        for west, east, code in [(106.699, 106.7002, 'ODT'), (106.6998, 106.701, ' ODT ')]:
            connection.execute('''INSERT INTO parcels.land_plot
                (uniq_id,mdsdd,tile_z,tile_x,tile_y,geom)
                VALUES (%s,%s,16,0,0,ST_MakeEnvelope(%s,10.799,%s,10.801,4326))''',
                (key, code, west, east))
        connection.execute('REFRESH MATERIALIZED VIEW parcels.plot')
        row = connection.execute('''SELECT id,source_fragments,ST_Area(geom),area_m2
            FROM parcels.plot WHERE uniq_id=%s''', (key,)).fetchone()
        assert row[1] == 2
        assert row[2] == pytest.approx(0.000004, rel=1e-7), 'overlap must not count twice'
        connection.execute("INSERT INTO public.layer_snapshots(layer,metadata) VALUES ('land_price','{}') ON CONFLICT DO NOTHING")
        connection.execute('''INSERT INTO public.layer_features(layer,feature_id,geom,properties)
            VALUES ('land_price',%s,ST_GeomFromText('LINESTRING(106.699 10.799,106.701 10.799)',4326),%s)''',
            (key, Jsonb(road()['properties'])))
        for zoom in (12, 14, 16):
            tile = mercantile.tile(106.7, 10.8, zoom)
            decoded = mapbox_vector_tile.decode(parcels.vector_tile(zoom, tile.x, tile.y))
            matches = [f for f in decoded['features']['features'] if f['properties']['parcel_id'] == str(row[0])]
            assert len(matches) == 1
            assert matches[0]['properties']['color'] == '#D79B8C'
        assert parcels.vector_tile(11, 0, 0) == b''
        response = TestClient(app).get(f'/api/v1/parcels/{row[0]}')
        assert response.status_code == 200
        body = response.json()
        assert body['parcel']['source_fragments'] == 2
        assert body['price']['unit_price_vnd_m2'] == 10_000_000
        assert body['price']['estimated_land_total_vnd'] == round(row[3] * 10_000_000)
        assert body['price']['price_category'] == 'Residential'
        assert body['price']['road_match_status'] == 'spatially_checked'
        assert body['price']['provenance'] == 'Published road-price layer'
    finally:
        connection.rollback()
        connection.close()
