import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.routers.population.warehouse_configured", lambda: True)
    monkeypatch.setattr("app.routers.layers.warehouse_configured", lambda: True)
    return TestClient(app)


def test_api_discovery_documents_map_services(client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/layers/{layer}/tiles/{z}/{x}/{y}.pbf" in paths
    assert "/api/v1/population/{year}/tiles/{z}/{x}/{y}.png" in paths
    assert "/api/v1/population/{year}/value" in paths
    assert "/api/v1/population/{year}/stats" in paths


@pytest.mark.parametrize(
    ("loaded_layers", "loaded_population_years", "expected_status"),
    [(0, 1, 200), (1, 0, 200), (0, 0, 503)],
)
def test_readiness_accepts_any_published_map_data(
    client, monkeypatch, loaded_layers, loaded_population_years, expected_status
):
    monkeypatch.setattr(
        "app.main.readiness",
        lambda: {
            "storage": "postgis",
            "loaded_layers": loaded_layers,
            "loaded_population_years": loaded_population_years,
        },
    )
    assert client.get("/ready").status_code == expected_status


def test_population_catalog_and_years(client, monkeypatch):
    loaded = [
        {
            "year": 2022,
            "tile_count": 64,
            "sources": ["worldpop_2022.tif"],
            "loaded_at": "2026-10-05T12:00:00+00:00",
        }
    ]
    monkeypatch.setattr("app.repository.population_years", lambda: loaded)

    catalog = client.get("/api/v1/urban/population")
    assert catalog.status_code == 200
    assert catalog.json()["available"] is True
    assert catalog.json()["years"] == loaded
    assert catalog.json()["unit"] == "persons per source raster cell"
    assert client.get("/api/v1/population/years").json() == {"years": loaded}


def test_population_tilejson_uses_request_host_and_xyz_template(client, monkeypatch):
    monkeypatch.setattr(
        "app.repository.population_years",
        lambda: [{"year": 2022, "tile_count": 4, "sources": [], "loaded_at": "now"}],
    )

    result = client.get("/api/v1/population/2022/tilejson.json").json()
    assert result["format"] == "png"
    assert result["scheme"] == "xyz"
    assert result["tiles"] == [
        "http://testserver/api/v1/population/2022/tiles/{z}/{x}/{y}.png?palette=pseudocolor&render=2"
    ]


def test_population_png_tile_etag_and_invalid_xyz(client, monkeypatch):
    monkeypatch.setattr(
        "app.repository.population_years",
        lambda: [{"year": 2022, "tile_count": 4, "sources": [], "loaded_at": "now"}],
    )
    samples = [[12.0] * 256 for _ in range(256)]
    monkeypatch.setattr("app.repository.population_tile", lambda *args: samples)

    url = "/api/v1/population/2022/tiles/2/1/2.png"
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["etag"]
    assert 'population-v2-' in response.headers['etag']
    cached = client.get(url, headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    assert client.get("/api/v1/population/2022/tiles/2/4/0.png").status_code == 404


def test_population_value_and_viewport_stats(client, monkeypatch):
    monkeypatch.setattr(
        "app.repository.population_years",
        lambda: [{"year": 2022, "tile_count": 4, "sources": [], "loaded_at": "now"}],
    )
    monkeypatch.setattr("app.repository.population_value", lambda *args: 18.5)
    monkeypatch.setattr(
        "app.repository.population_statistics",
        lambda year, bounds: {
            "pixel_count": 2,
            "population_sum": 20,
            "population_mean_per_pixel": 10,
            "population_stddev_per_pixel": 0,
            "population_min_per_pixel": 5,
            "population_max_per_pixel": 15,
        },
    )

    sample = client.get("/api/v1/population/2022/value?lng=106.7&lat=10.8").json()
    assert sample["population"] == 18.5
    assert sample["coordinates"] == [106.7, 10.8]
    assert sample["nodata"] is False
    stats = client.get("/api/v1/population/2022/stats?bbox=106.6,10.7,106.8,10.9")
    assert stats.status_code == 200
    assert stats.json()["statistics"]["pixel_count"] == 2
    assert client.get("/api/v1/population/2022/stats?bbox=bad").status_code == 400
    assert client.get("/api/v1/population/2022/stats?bbox=0,0,20,20").status_code == 400


def test_population_renderer_returns_transparent_png_for_nodata():
    from io import BytesIO

    import numpy as np
    from PIL import Image

    from app.services.raster_tiles import render_population_tile

    samples = [[None] * 256 for _ in range(256)]
    samples[0][0] = 0
    samples[0][1] = 10
    samples[0][2] = 500
    image = Image.open(BytesIO(render_population_tile(samples, "pseudocolor")))
    pixels = np.asarray(image)
    assert image.size == (256, 256)
    assert pixels[0, 0, 3] == 0
    assert pixels[0, 1, 3] == 190
    assert pixels[1, 1, 3] == 0


def test_vector_tiles_are_mapbox_tiles_and_have_snapshot_etags(client, monkeypatch):
    monkeypatch.setattr(
        "app.repository.metadata",
        lambda layer: {"updated_at": "2026-10-06T00:00:00+00:00"},
    )
    monkeypatch.setattr("app.repository.vector_tile", lambda *args: b"mvt-content")

    response = client.get("/api/v1/layers/flood_history/tiles/2/1/1.pbf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert response.headers["etag"]
    cached = client.get(
        "/api/v1/layers/flood_history/tiles/2/1/1.pbf",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert cached.status_code == 304
    assert client.get("/api/v1/layers/not-a-layer/tiles/2/1/1.pbf").status_code == 404


def test_generated_buildings_are_exposed_as_streamed_vector_tiles(client, monkeypatch):
    monkeypatch.setattr(
        "app.repository.metadata",
        lambda layer: {"updated_at": "2026-10-13T00:00:00+00:00"},
    )
    monkeypatch.setattr("app.repository.vector_tile", lambda *args: b"building-tile")

    tilejson = client.get("/api/v1/layers/synthetic_buildings/tilejson.json")
    assert tilejson.status_code == 200
    assert tilejson.json()["minzoom"] == 14
    assert "synthetic_buildings" in tilejson.json()["tiles"][0]
    tile = client.get("/api/v1/layers/synthetic_buildings/tiles/14/13205/7475.pbf")
    assert tile.status_code == 200
    assert tile.content == b"building-tile"
    assert tile.headers["content-type"] == "application/vnd.mapbox-vector-tile"


def test_static_land_price_layer_rejects_time_filters(client):
    response = client.get(
        "/api/v1/layers/land_price/features",
        params={"start": datetime(2026, 1, 1, tzinfo=UTC).isoformat()},
    )
    assert response.status_code == 400


@pytest.mark.skipif(
    os.getenv("POSTGIS_TESTS") != "1",
    reason="PostGIS map tile integration checks are not enabled",
)
def test_postgis_vector_and_population_map_queries():
    import math
    import uuid

    from psycopg.types.json import Jsonb
    from src.shared.database import connect_to_warehouse

    from app import repository

    test_layer = f"api_test_{uuid.uuid4().hex}"
    test_year = 2199
    with connect_to_warehouse() as connection:
        occupied = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM population.population_raster WHERE year=%s)",
            (test_year,),
        ).fetchone()[0]
        assert not occupied, "Reserved integration-test raster year is already in use"
        connection.execute(
            """
            INSERT INTO public.layer_snapshots (layer, metadata)
            VALUES (%s, %s)
            """,
            (test_layer, Jsonb({"source": "isolated API integration fixture"})),
        )
        connection.execute(
            """
            INSERT INTO public.layer_features (layer, feature_id, geom, properties, observed_at)
                VALUES (%s, 'point', ST_SetSRID(ST_MakePoint(106.7005, 10.8995), 4326),
                    %s, '2026-10-05T00:00:00Z')
            """,
            (test_layer, Jsonb({"label": "tile check", "nested": {"ignored": True}})),
        )
        connection.execute(
            """
            INSERT INTO population.population_raster (year, source_file, tile_index, rast)
            VALUES (
                %s, 'api-integration-fixture.tif', 1,
                ST_AddBand(
                    ST_MakeEmptyRaster(2, 2, 106.7, 10.9, 0.001, -0.001, 0, 0, 4326),
                    '32BF'::text, 25::double precision, -9999::double precision
                )
            )
            """,
            (test_year,),
        )

    zoom = 10
    count = 2**zoom
    longitude, latitude = 106.7005, 10.8995
    x = math.floor((longitude + 180) / 360 * count)
    y = math.floor((1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2 * count)
    try:
        assert repository.population_value(test_year, longitude, latitude) == 25
        samples = repository.population_tile(test_year, zoom, x, y)
        assert len(samples) == 256
        assert len(samples[0]) == 256
        assert any(value == 25 for row in samples for value in row)
        from app.services.raster_tiles import render_population_tile

        assert render_population_tile(samples, "pseudocolor").startswith(b"\x89PNG\r\n\x1a\n")
        summary = repository.population_statistics(test_year, (106.69, 10.89, 106.71, 10.91))
        assert summary["pixel_count"] == 4
        assert summary["population_sum"] == 100
        assert repository.vector_tile(test_layer, zoom, x, y)
    finally:
        with connect_to_warehouse() as connection:
            connection.execute("DELETE FROM public.layer_features WHERE layer=%s", (test_layer,))
            connection.execute("DELETE FROM public.layer_snapshots WHERE layer=%s", (test_layer,))
            connection.execute(
                "DELETE FROM population.population_raster WHERE year=%s", (test_year,)
            )
