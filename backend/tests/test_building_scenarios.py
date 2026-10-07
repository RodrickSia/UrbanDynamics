import copy
import json
import os
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.simulation.engine import calculate, polygon_and_area
from app.services.simulation.models import BuildingScenario, PolygonInput


SITE = {"type": "Polygon", "coordinates": [
    [[106.76, 10.82], [106.761, 10.82], [106.761, 10.821], [106.76, 10.821], [106.76, 10.82]]
]}


@pytest.fixture
def payload():
    _, area = polygon_and_area(PolygonInput(**SITE))
    def variant(shares, storage=0):
        return {**{f"{s}_m2": area * share for s, share in
                   zip(("roof", "paved", "permeable", "green"), shares)},
                "available_storage_m3": storage, "floors": 3, "users": 600}
    return {
        "title": "Synthetic school design", "building_use": "school", "site": copy.deepcopy(SITE),
        "rainfall_mm": 60, "coefficients": {"roof": .9, "paved": .85, "permeable": .35, "green": .2},
        "coefficient_basis": "Synthetic coefficients for software tests; not calibrated",
        "design_basis": "Synthetic geometry and designs; no survey data",
        "baseline": variant([0, .1, .2, .7]), "development": variant([.3, .5, .1, .1]),
        "mitigated": variant([.3, .2, .2, .3], 80),
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("WAREHOUSE_PASSWORD", raising=False); monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SCENARIO_DATA_DIR", str(tmp_path / "scenarios"))
    return TestClient(app)


def test_known_volume_and_before_after_conservation(payload):
    result = calculate(BuildingScenario(**payload))
    area = result["site_area_m2"]
    assert 12000 < area < 12200  # WGS84 reference rectangle near Thu Duc.
    assert result["variants"]["baseline"]["gross_runoff_m3"] == pytest.approx(.06 * area * .295)
    assert result["variants"]["development"]["gross_runoff_m3"] == pytest.approx(.06 * area * .75)
    assert result["variants"]["mitigated"]["gross_runoff_m3"] == pytest.approx(.06 * area * .57)
    for variant in result["variants"].values():
        assert variant["gross_runoff_m3"] == pytest.approx(variant["retained_m3"] + variant["unretained_runoff_m3"])
        assert variant["gross_runoff_m3"] <= variant["rainfall_volume_m3"]
    comparison = result["comparisons"][2]
    assert comparison["delta"]["unretained_runoff_m3"] == pytest.approx(-.06 * area * .18 - 80)
    assert result["assessment_level"] == "uncalibrated_screening"
    assert "flood_depth" in result["unavailable_modules"]


def test_unchanged_design_has_zero_delta_and_repeatable_digest(payload):
    payload["development"] = copy.deepcopy(payload["baseline"])
    payload["mitigated"] = copy.deepcopy(payload["baseline"])
    before = copy.deepcopy(payload)
    result = calculate(BuildingScenario(**payload))
    assert all(all(value == 0 for value in item["delta"].values()) for item in result["comparisons"])
    assert result == calculate(BuildingScenario(**payload))
    assert payload == before


@pytest.mark.parametrize("rain", [0, 60])
def test_storage_never_produces_negative_runoff(payload, rain):
    payload["rainfall_mm"] = rain
    payload["baseline"]["available_storage_m3"] = 1_000_000
    result = calculate(BuildingScenario(**payload))
    assert result["variants"]["baseline"]["unretained_runoff_m3"] == 0
    assert result["comparisons"][0]["unretained_runoff_change_pct"] is None


def test_geodesic_area_excludes_holes_and_is_orientation_independent():
    outer = copy.deepcopy(SITE)
    hole = [[106.7602,10.8202],[106.7602,10.8208],[106.7608,10.8208],[106.7608,10.8202],[106.7602,10.8202]]
    holed = copy.deepcopy(SITE)
    holed["coordinates"].append(hole)
    _, expected = polygon_and_area(PolygonInput(**outer))
    _, excluded = polygon_and_area(PolygonInput(type="Polygon", coordinates=[hole]))
    _, actual = polygon_and_area(PolygonInput(**holed))
    assert actual == pytest.approx(expected - excluded, abs=.001)
    holed["coordinates"] = [list(reversed(r)) for r in holed["coordinates"]]
    assert polygon_and_area(PolygonInput(**holed))[1] == pytest.approx(actual, abs=.001)


def test_building_inside_site_and_footprint_area_consistency(payload):
    footprint = {"type": "Polygon", "coordinates": [
        [[106.7601,10.8201],[106.7604,10.8201],[106.7604,10.8204],[106.7601,10.8204],[106.7601,10.8201]]
    ]}
    _, area = polygon_and_area(PolygonInput(**footprint))
    variant = payload["development"]
    variant["green_m2"] += variant["roof_m2"] - area
    variant["roof_m2"] = area
    variant["footprint"] = footprint
    result = calculate(BuildingScenario(**payload))
    assert len(result["map"]["features"]) == 2
    # Move the same-size footprint outside; volume totals still valid but geometry is rejected.
    variant["footprint"]["coordinates"] = [[(x+.01,y) for x,y in footprint["coordinates"][0]]]
    with pytest.raises(ValueError, match="inside the site"):
        calculate(BuildingScenario(**payload))


def test_scenario_is_saved_retrievable_and_new_runs_do_not_replace_old(client, payload):
    created = client.post("/api/v1/scenarios/building", json=payload)
    assert created.status_code == 201
    result = created.json()
    assert client.get(f"/api/v1/scenarios/building/{result['id']}").json() == result
    payload["rainfall_mm"] = 100
    changed = client.post("/api/v1/scenarios/building", json=payload).json()
    assert changed["id"] != result["id"]
    assert changed["input_sha256"] != result["input_sha256"]
    assert client.get(f"/api/v1/scenarios/building/{result['id']}").json() == result
    assert client.get(f"/api/v1/scenarios/building/{uuid4()}").status_code == 404
    assert client.get("/api/v1/scenarios/building/not-a-uuid").status_code == 422


@pytest.mark.parametrize("field,value", [("rainfall_mm", -1), ("rainfall_mm", 1001),
                                        ("coefficient_basis", "     "), ("building_use", "unknown")])
def test_invalid_context_rejected(client, payload, field, value):
    payload[field] = value
    assert client.post("/api/v1/scenarios/building", json=payload).status_code == 422


@pytest.mark.parametrize("mutation", ["coefficient", "extra", "area", "negative", "footprint", "unclosed", "crossed", "oversized", "latitude"])
def test_invalid_design_and_geometry_rejected(client, payload, mutation):
    if mutation == "coefficient": payload["coefficients"]["roof"] = 1.1
    if mutation == "extra": payload["development"]["made_up_depth"] = 1
    if mutation == "area": payload["development"]["green_m2"] += 10
    if mutation == "negative": payload["mitigated"]["available_storage_m3"] = -1
    if mutation == "footprint": payload["development"]["footprint"] = copy.deepcopy(SITE)
    if mutation == "unclosed": payload["site"]["coordinates"][0].pop()
    if mutation == "crossed": payload["site"]["coordinates"][0] = [[106.76,10.82],[106.761,10.821],[106.761,10.82],[106.76,10.821],[106.76,10.82]]
    if mutation == "oversized": payload["site"]["coordinates"][0] = [[106,10],[107,10],[107,11],[106,11],[106,10]]
    if mutation == "latitude": payload["site"]["coordinates"][0][1][1] = 100
    response = client.post("/api/v1/scenarios/building", json=payload)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("value", ["NaN", "Infinity", '"NaN"'])
def test_nonfinite_numbers_are_rejected(client, payload, value):
    # String form is valid JSON; bare forms are accepted by Python's JSON parser.
    content = json.dumps(payload).replace('"rainfall_mm": 60', f'"rainfall_mm": {value}')
    assert client.post("/api/v1/scenarios/building", content=content,
                       headers={"Content-Type": "application/json"}).status_code == 422


def test_storage_failure_is_safe_and_does_not_fallback_to_files(client, payload, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "configured-database")
    def unavailable(*args, **kwargs):
        raise psycopg.OperationalError("private connection details")
    monkeypatch.setattr("app.services.simulation.store.psycopg.connect", unavailable)
    for response in (client.post("/api/v1/scenarios/building", json=payload),
                     client.get(f"/api/v1/scenarios/building/{uuid4()}")):
        assert response.status_code == 503
        assert "private" not in response.text
    assert not (tmp_path / "scenarios").exists()


def test_demo_and_area_api_available(client):
    assert client.get("/simulation").status_code == 200
    assert client.get("/simulation.js").status_code == 200
    response = client.post("/api/v1/scenarios/site-area", json=SITE)
    assert response.status_code == 200
    assert response.json()["units"] == "m2"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires real PostGIS")
@pytest.mark.parametrize("configuration", ["url", "warehouse"])
def test_postgis_persistence_and_site_geometry(payload, monkeypatch, configuration):
    url = os.environ["TEST_DATABASE_URL"]
    if configuration == "url":
        monkeypatch.setenv("DATABASE_URL", url)
    else:
        from psycopg.conninfo import conninfo_to_dict
        settings = conninfo_to_dict(url)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for key, name in {"host": "HOST", "port": "PORT", "dbname": "DATABASE", "user": "USER", "password": "PASSWORD"}.items():
            monkeypatch.setenv("WAREHOUSE_" + name, settings[key])
    client = TestClient(app)
    identifier = None
    try:
        response = client.post("/api/v1/scenarios/building", json=payload)
        assert response.status_code == 201
        data = response.json()
        identifier = UUID(data["id"])
        assert client.get(f"/api/v1/scenarios/building/{identifier}").json() == data
        with psycopg.connect(url) as connection:
            row = connection.execute("SELECT ST_SRID(site),ST_IsValid(site),input_sha256,document "
                                     "FROM building_scenario_runs WHERE id=%s", (identifier,)).fetchone()
        assert row[0:2] == (4326, True)
        assert row[2] == data["input_sha256"]
        assert row[3] == data
    finally:
        if identifier:
            with psycopg.connect(url) as connection:
                connection.execute("DELETE FROM building_scenario_runs WHERE id=%s", (identifier,))
