"""Building map endpoints expose only the loaded GBA LoD1 snapshot."""

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import buildings as router

client = TestClient(app)


def test_snapshot_reports_loaded_gba_model(monkeypatch):
    monkeypatch.setattr(router, "warehouse_configured", lambda: True)
    monkeypatch.setattr(router.buildings, "snapshot", lambda: {
        "feature_count": 42, "loaded_at": "2026-01-01T00:00:00+00:00"})
    response = client.get("/api/v1/buildings/snapshot")
    assert response.status_code == 200
    assert response.json()["source"] == "hcmc_gba_lod1"
    assert response.json()["feature_count"] == 42


def test_unloaded_model_does_not_claim_availability(monkeypatch):
    monkeypatch.setattr(router, "warehouse_configured", lambda: True)
    monkeypatch.setattr(router.buildings, "snapshot", lambda: None)
    assert client.get("/api/v1/buildings/snapshot").status_code == 404


def test_building_tiles_validate_matrix_and_return_vector_bytes(monkeypatch):
    monkeypatch.setattr(router, "warehouse_configured", lambda: True)
    monkeypatch.setattr(router.buildings, "vector_tile", lambda z, x, y: b"building-mvt")
    response = client.get("/api/v1/buildings/tiles/14/13042/7449.pbf")
    assert response.status_code == 200
    assert response.content == b"building-mvt"
    assert response.headers["content-type"].startswith("application/vnd.mapbox-vector-tile")
    assert client.get("/api/v1/buildings/tiles/14/16384/0.pbf").status_code == 404
    assert client.get("/api/v1/buildings/tiles/17/0/0.pbf").status_code == 404


def test_missing_warehouse_and_empty_tile(monkeypatch):
    monkeypatch.setattr(router, "warehouse_configured", lambda: False)
    assert client.get("/api/v1/buildings/snapshot").status_code == 503
    monkeypatch.setattr(router, "warehouse_configured", lambda: True)
    monkeypatch.setattr(router.buildings, "vector_tile", lambda z, x, y: b"")
    assert client.get("/api/v1/buildings/tiles/14/13042/7449.pbf").status_code == 204


@pytest.mark.skipif(os.getenv("POSTGIS_TESTS") != "1", reason="Requires isolated PostGIS")
def test_tile_clips_only_confident_parcel_matches(monkeypatch):
    import mapbox_vector_tile
    import mercantile
    from shapely.geometry import shape
    from src.shared.database import connect_to_warehouse

    connection = connect_to_warehouse()
    key = uuid4().hex

    @contextmanager
    def same_transaction():
        yield connection

    monkeypatch.setattr(router.buildings, "connect_to_warehouse", same_transaction)
    try:
        connection.execute("""
            INSERT INTO parcels.land_plot (uniq_id, mdsdd, tile_z, tile_x, tile_y, geom)
            VALUES (%s, 'ODT', 16, 0, 0,
                    ST_MakeEnvelope(106.69953, 10.7985, 106.70047, 10.8005, 4326))
        """, (key,))
        connection.execute("REFRESH MATERIALIZED VIEW parcels.plot")
        for suffix, west, east in (("matched", 106.6995, 106.7005),
                                   ("unmatched", 106.701, 106.7013)):
            connection.execute("""
                INSERT INTO buildings.gba_lod1
                    (feature_id, gba_id, source_tile, height_m, geom)
                VALUES (%s, %s, 'fixture', 20,
                        ST_Multi(ST_MakeEnvelope(%s, 10.7985, %s, 10.8005, 4326)))
            """, (f"{key}-{suffix}", f"{key}-{suffix}", west, east))

        tile = mercantile.tile(106.7, 10.8, 16)
        decoded = mapbox_vector_tile.decode(
            router.buildings.vector_tile(16, tile.x, tile.y))['buildings']['features']
        ours = {item['properties']['feature_id']: item for item in decoded
                if item['properties']['feature_id'].startswith(key)}
        assert ours[f"{key}-matched"]['properties']['parcel_fit'] == 'matched'
        assert ours[f"{key}-unmatched"]['properties']['parcel_fit'] == 'source_unmatched'

        bounds = mercantile.xy_bounds(tile)
        def pixel_x(lon):
            return (mercantile.xy(lon, 10.8)[0] - bounds.left) / (bounds.right - bounds.left) * 4096

        aligned_bounds = shape(ours[f"{key}-matched"]['geometry']).bounds
        source_bounds = shape(ours[f"{key}-unmatched"]['geometry']).bounds
        assert aligned_bounds[0] == pytest.approx(pixel_x(106.69953), abs=2)
        assert aligned_bounds[2] == pytest.approx(pixel_x(106.70047), abs=2)
        assert source_bounds[0] == pytest.approx(pixel_x(106.701), abs=2)

        distant = mercantile.tile(106.7, 10.8, 14)
        distant_features = mapbox_vector_tile.decode(
            router.buildings.vector_tile(14, distant.x, distant.y))['buildings']['features']
        distant_ours = {item['properties']['feature_id']: item['properties']['parcel_fit']
                       for item in distant_features if item['properties']['feature_id'].startswith(key)}
        assert distant_ours[f"{key}-matched"] == 'matched'
        assert distant_ours[f"{key}-unmatched"] == 'source_unmatched'

        # Identity may establish a correction even with no initial overlap.
        connection.execute("""
            INSERT INTO buildings.gba_lod1
                (feature_id, gba_id, source, source_id, source_tile, height_m, geom)
            VALUES (%s, %s, 'google', %s, 'fixture', 46,
                    ST_Multi(ST_MakeEnvelope(106.6992, 10.799, 106.6993, 10.7991, 4326)))
        """, (f'{key}-identity', key, key))
        connection.execute("""
            INSERT INTO buildings.footprint (overture_id, source_release, properties, geom)
            VALUES (%s, 'fixture', jsonb_build_object('sources', jsonb_build_array(
                jsonb_build_object('dataset', 'Google Open Buildings', 'property', '', 'record_id', %s::text))),
                ST_Multi(ST_MakeEnvelope(106.6996, 10.799, 106.6997, 10.7991, 4326)))
        """, (key, key))
        corrected = mapbox_vector_tile.decode(
            router.buildings.vector_tile(16, tile.x, tile.y))['buildings']['features']
        identity = next(f for f in corrected if f['properties']['feature_id'] == f'{key}-identity')
        assert identity['properties']['geometry_source'] == 'overture'
        assert identity['properties']['overture_id'] == key
        assert identity['properties']['match_method'] == 'source_identity'
        assert identity['properties']['height_m'] == 46
        assert shape(identity['geometry']).bounds[0] == pytest.approx(pixel_x(106.6996), abs=2)
    finally:
        connection.rollback()
        connection.close()
