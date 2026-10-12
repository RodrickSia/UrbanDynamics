"""Building map endpoints expose only the loaded GBA LoD1 snapshot."""

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
