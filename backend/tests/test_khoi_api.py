import os
import uuid
from datetime import datetime, timedelta, timezone

import geopandas as gpd
import pytest
from app.main import app
from fastapi.testclient import TestClient
from shapely.geometry import Point
from src.pipelines.flood_history.transform import transform_frame
from src.shared.data_io import write_json
from src.shared.database import connect_to_warehouse, publish


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("WAREHOUSE_PASSWORD", raising=False)
    frame = gpd.GeoDataFrame(
        {
            "Obs_id": ["one", "two"],
            "Date": ["14/09/2019", "01/10/2020"],
            "Location name": ["One", "Two"],
        },
        geometry=[Point(106.76, 10.82), Point(107, 11)],
        crs=4326,
    )
    publish("flood_history", transform_frame(frame))
    return TestClient(app), tmp_path


def test_api_spatial_and_time_filters(client):
    api, _ = client
    result = api.get(
        "/api/v1/floods/history",
        params={"bbox": "106.7,10.7,106.9,10.9", "end": "2020-01-01T00:00:00Z"},
    )
    assert result.status_code == 200
    assert [f["id"] for f in result.json()["features"]] == ["one"]


@pytest.mark.parametrize("bbox", ["bad", "0,0,1", "1,2,0,3", "0,0,nan,1", "-181,0,1,2"])
def test_bad_bbox_is_rejected(client, bbox):
    assert (
        client[0].get("/api/v1/floods/history", params={"bbox": bbox}).status_code
        == 400
    )


def test_database_outage_returns_503_without_connection_details(client, monkeypatch):
    import psycopg

    def unavailable(*args):
        raise psycopg.OperationalError("secret connection details")

    monkeypatch.setattr("app.repository.metadata", unavailable)
    for route in ("/api/v1/layers", "/api/v1/floods/history"):
        response = client[0].get(route)
        assert response.status_code == 503
        assert "secret" not in response.text


def test_price_rows_report_corrupt_snapshot(client):
    api, root = client
    path = root / "review/land_price_rows.json"
    path.parent.mkdir()
    path.write_text("invalid-json", encoding="utf-8")
    assert api.get("/api/v1/land-prices/rows").status_code == 503


def test_api_reports_truncation_and_missing_layer(client):
    api, _ = client
    result = api.get("/api/v1/floods/history", params={"limit": 1}).json()
    assert result["metadata"]["truncated"]
    assert api.get("/api/v1/land-prices").status_code == 503
    assert api.get("/api/v1/layers/unknown/features").status_code == 404


def test_ready_and_layer_catalog(client):
    api, _ = client
    assert api.get("/ready").status_code == 200
    layers = api.get("/api/v1/layers").json()["layers"]
    assert next(f for f in layers if f["id"] == "flood_history")["available"]
    assert not next(f for f in layers if f["id"] == "flood_satellite")["available"]


def test_scenario_validates_and_preserves_historical_layer(client):
    api, root = client
    issued = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def station(start, count, amount):
        return {
            "id": "s",
            "longitude": 106.76,
            "latitude": 10.82,
            "hourly": [
                {
                    "time": (start + timedelta(hours=i)).isoformat(),
                    "precipitation_mm": amount,
                }
                for i in range(count)
            ],
        }

    write_json(
        root / "inputs" / "rainfall_forecast.json",
        {"issued_at": issued.isoformat(), "stations": [station(issued, 6, 3)]},
    )
    write_json(
        root / "inputs" / "rainfall_history.json",
        {"stations": [station(issued.replace(year=2025, day=1), 100, 1)]},
    )
    before = (root / "layers" / "flood_history.geojson").read_bytes()
    result = api.post("/api/v1/scenarios/rain", json={"rain_3h_mm": 60})
    assert result.status_code == 200
    assert result.json()["features"][0]["properties"]["scenario"]
    assert (root / "layers" / "flood_history.geojson").read_bytes() == before
    assert (
        api.post("/api/v1/scenarios/rain", json={"rain_3h_mm": -1}).status_code == 422
    )


def test_scenario_without_weather_is_unavailable(client):
    assert (
        client[0].post("/api/v1/scenarios/rain", json={"rain_3h_mm": 60}).status_code
        == 503
    )


def test_api_reads_the_shared_postgis_layer():
    if os.getenv("POSTGIS_TESTS") != "1":
        pytest.skip("PostGIS integration checks are not enabled")
    from src.shared.database import read_layer_document

    layer = "flood_history"
    try:
        previous = read_layer_document(layer)
    except FileNotFoundError:
        previous = None
    document = {
        "type": "FeatureCollection",
        "metadata": {"layer": layer},
        "features": [
            {
                "type": "Feature",
                "id": "api-" + uuid.uuid4().hex,
                "geometry": {"type": "Point", "coordinates": [106.76, 10.82]},
                "properties": {
                    "observed_at": "2024-01-01T00:00:00Z",
                    "location": "Shared warehouse",
                },
            }
        ],
    }
    try:
        publish(layer, document)
        response = TestClient(app).get("/api/v1/floods/history")
        assert response.status_code == 200
        assert any(
            feature["properties"].get("location") == "Shared warehouse"
            for feature in response.json()["features"]
        )
    finally:
        if previous is not None:
            publish(layer, previous)
        else:
            with connect_to_warehouse() as connection:
                connection.execute(
                    "DELETE FROM layer_features WHERE layer=%s", (layer,)
                )
                connection.execute(
                    "DELETE FROM layer_snapshots WHERE layer=%s", (layer,)
                )
