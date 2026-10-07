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


def test_planning_breakdown_keeps_source_areas_without_fabricating_percentages():
    rows = parcels.planning_breakdown('Đất ở: 180.9 m2; Đất giao thông: 10.8 m2; Unknown')
    assert rows == [{'label': 'Đất ở', 'area_m2': 180.9}, {'label': 'Đất giao thông', 'area_m2': 10.8}]


def test_palette_uses_source_sample_and_normalizes_unknown():
    assert parcels.land_use('OTC')['color'] == '#e85430'
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
            assert matches[0]['properties']['color'] == '#d6604d'
        assert parcels.vector_tile(11, 0, 0) == b''
        response = TestClient(app).get(f'/api/v1/parcels/{row[0]}')
        assert response.status_code == 200
        body = response.json()
        assert body['parcel']['source_fragments'] == 2
        assert body['price']['unit_price_vnd_m2'] == 10_000_000
        assert body['price']['estimated_land_total_vnd'] == round(row[3] * 10_000_000)
    finally:
        connection.rollback()
        connection.close()
