"""Coverage, integrity, source attribution and native OSM import regression."""
import copy
import json

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape

from app.main import app
from app.routers.integrated_scenarios import demo_payload
from app.services.simulation.integrated import background, geometry, solvers
from app.services.simulation.integrated.context import build_context
from app.services.simulation.integrated.models import IntegratedRequest, Design, Baseline
from app.services.simulation.integrated.library import parameters


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for key in ("WAREHOUSE_PASSWORD", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SIMULATION_SNAPSHOT_DIR", str(tmp_path/"snapshots"))
    monkeypatch.setenv("SCENARIO_DATA_DIR", str(tmp_path/"runs"))
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path/"engines"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path/"data"))


def extract():
    nodes = {1: (106.755, 10.819), 2: (106.760, 10.819), 3: (106.765, 10.819), 4: (106.760, 10.815), 5: (106.760, 10.825)}
    elements = [{"type": "node", "id": identifier, "lon": p[0], "lat": p[1],
                 "tags": {"highway": "traffic_signals"} if identifier == 2 else {}} for identifier, p in nodes.items()]
    for identifier, ids in ((100, [1, 2, 3]), (101, [4, 2, 5])):
        elements.append({"type": "way", "id": identifier, "nodes": ids,
                         "geometry": [{"lon": nodes[i][0], "lat": nodes[i][1]} for i in ids],
                         "tags": {"highway": "residential", "lanes": "2", "maxspeed": "40"}})
    elements.append({"type": "node", "id": 9, "lon": 106.760, "lat": 10.824, "tags": {"amenity": "school", "name": "Fixture school"}})
    elements.append({"type": "way", "id": 200, "nodes": [21, 22, 23, 24, 21],
                     "geometry": [{"lon": x, "lat": y} for x, y in demo_payload()["development"]["buildings"][0]["footprint"]["coordinates"][0]],
                     "tags": {"building": "apartments", "building:levels": "2", "height": "6"}})
    return {"elements": elements}


def snapshot():
    return {"schema_version": 1, "captured_at": "2026-10-11T00:00:00+00:00",
            "bbox": [106.75, 10.81, 106.77, 10.83], "osm": extract(),
            "population": {"year": 2025, "bbox": [106.75, 10.81, 106.77, 10.83],
                           "statistics": {"pixel_count": 100, "population_sum": 1500}, "source": "Test population raster estimate"},
            "parcels": {"features": [{"type": "Feature", "geometry": demo_payload()["site"], "properties": {"mdsdd": "ODT"}}],
                        "metadata": {"truncated": False}}, "sources": {"osm": {"license": "ODbL-1.0"}}, "layers": {}}


def request_with_snapshot():
    identifier = background.publish(snapshot())
    payload = demo_payload()
    payload.update(data_mode="snapshot_required", snapshot_id=identifier)
    return IntegratedRequest(**payload)


def test_snapshot_changes_real_inputs_and_balances_baseline():
    request = request_with_snapshot()
    context = build_context(request)
    assert context["traffic_network_kind"] == "osm"
    assert context["background_population"] == 1500
    assert context["library"]["existing_service_users"] == 375
    assert context["baseline"]["buildings"][0]["floors"] == 2
    assert context["baseline"]["buildings"][0]["residents"] == 0
    assert context["baseline_provenance"]["buildings"][0]["occupancy"] == "unknown_assumed_zero"
    geometry.analyze(request.site, Design(**context["baseline"]))
    assert context["services"][0]["properties"]["capacity"] is None
    assert context["services"][0]["properties"]["network_distance_m"] > 0
    assert len(context["data_inventory"]["site_parcels"]["features"]) == 1


def test_explicit_synthetic_mode_ignores_published_data():
    request = request_with_snapshot()
    request.data_mode = "synthetic"
    context = build_context(request)
    assert context["traffic_network_kind"] == "synthetic"
    assert context["background_population"] == 1200
    assert context["baseline_provenance"]["kind"] == "synthetic"


def test_user_baseline_overrides_map_estimate():
    request = request_with_snapshot()
    request.baseline = Baseline(
        design=request.development, source="Surveyed pilot design supplied by user")
    context = build_context(request)
    assert context["baseline"] == request.development.model_dump(mode="json")
    assert context["baseline_provenance"]["kind"] == "user_supplied"


def test_snapshot_integrity_and_missing_coverage_rejected():
    request = request_with_snapshot()
    path = background.snapshot_directory()/f"{request.snapshot_id}.json"
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError, match="integrity"):
        build_context(request)
    request.snapshot_id = "a"*64
    with pytest.raises(ValueError, match="covers"):
        build_context(request)


def test_snapshot_outside_site_rejected():
    document = snapshot()
    document["bbox"] = [105, 9, 105.1, 9.1]
    payload = demo_payload()
    payload["snapshot_id"] = background.publish(document)
    with pytest.raises(ValueError, match="covers"):
        build_context(IntegratedRequest(**payload))


def test_future_population_not_treated_as_current():
    document = snapshot()
    document["population"]["year"] = 2200
    payload = demo_payload()
    payload["snapshot_id"] = background.publish(document)
    context = build_context(IntegratedRequest(**payload))
    assert context["background_population"] == 1200
    assert context["population_provenance"]["kind"] == "synthetic"


def test_mismatched_population_scope_rejected():
    document = snapshot()
    document['population']['bbox'] = [100, 0, 110, 20]
    payload = demo_payload()
    payload['snapshot_id'] = background.publish(document)
    with pytest.raises(ValueError, match='bounding box'):
        build_context(IntegratedRequest(**payload))


def test_pinned_snapshot_does_not_read_live_population(monkeypatch):
    request = request_with_snapshot()
    from app import repository
    import src.shared.database as db
    monkeypatch.setattr(db, 'warehouse_configured', lambda: True)
    monkeypatch.setattr(repository, 'population_years', lambda: pytest.fail('Pinned snapshot must use frozen population'))
    # Context's unrelated optional layer reads are stubbed; our snapshot has no layers.
    monkeypatch.setattr(repository, 'features', lambda *a, **k: {'features': [], 'metadata': {}})
    assert build_context(request)['background_population'] == 1500


def test_landcover_is_historical_proxy_not_roof_geometry():
    document = snapshot()
    document["landcover"] = {"metadata": {"year": 2021}, "features": [
        {"type": "Feature", "geometry": demo_payload()["site"], "properties": {"class_code": 50}}]}
    payload = demo_payload()
    payload["snapshot_id"] = background.publish(document)
    context = build_context(IntegratedRequest(**payload))
    assert len(context["baseline"]["buildings"]) == 1  # Only OSM footprint.
    assert context["baseline_provenance"]["built_up_paved_proxy_m2"] > 0
    assert context["baseline_provenance"]["unclassified_surface_m2"] < .1
    assert any("historical" in x for x in context["data_inventory"]["warnings"])


def test_empty_osm_does_not_establish_vacant_site():
    document = snapshot()
    document["osm"] = {"elements": []}
    payload = demo_payload()
    payload["snapshot_id"] = background.publish(document)
    context = build_context(IntegratedRequest(**payload))
    assert not context["baseline_provenance"]["coverage_complete"]
    assert "do not mean vacant" in context["baseline_provenance"]["limitations"]


def test_nested_numeric_provenance_does_not_claim_verified_rates():
    library = parameters("base")
    assert not library["parameter_validation"]["numeric_defaults_verified_from_references"]
    for key in ("uses.residential.water_l_person_day", "runoff_coefficients.roof", "profiles.residential", "swmm.horton_min_mm_hour"):
        assert library["parameter_provenance"][key]["numeric_source"] is None
    office = library["parameter_provenance"]["uses.office.energy_kwh_m2_day"]
    assert office["numeric_source"]["original_value"] == 116.4
    assert office["needs_local_calibration"]


def test_preflight_api_never_runs_native_solver(monkeypatch):
    request = request_with_snapshot()
    monkeypatch.setattr(solvers, "traffic", lambda *a: pytest.fail("Context API must not run SUMO"))
    response = TestClient(app).post("/api/v1/scenarios/integrated/context", json=request.model_dump(mode="json"))
    assert response.status_code == 200
    assert response.json()["traffic_network_kind"] == "osm"
    assert "source_osm" not in response.json()


def test_client_cannot_supply_paths_or_urls():
    payload = demo_payload()
    payload["snapshot_id"] = "../../secrets"
    assert TestClient(app).post("/api/v1/scenarios/integrated/context", json=payload).status_code == 422
    payload = demo_payload()
    payload["source_url"] = "http://localhost/private"
    assert TestClient(app).post("/api/v1/scenarios/integrated/context", json=payload).status_code == 422


def test_real_native_osm_import_common_hour_and_geojson():
    request = request_with_snapshot()
    client = TestClient(app)
    response = client.post("/api/v1/scenarios/integrated/predict", json=request.model_dump(mode="json"))
    assert response.status_code == 201, response.text
    result = response.json()
    before, after = (result["variants"][key] for key in ("baseline", "development"))
    assert before["traffic"]["peak_hour_local"] == after["traffic"]["peak_hour_local"]
    assert after["traffic"]["network_provenance"]["boundary_approaches"] >= 2
    assert after["traffic"]["kind"] == "mixed_osm_and_estimates"
    assert after["services"]["provenance"]["capacity_kind"].startswith("synthetic")
    assert result["context"]["library"]["background_vehicles_hour"] != 400
    assert result["assessment"]["rows"][0]["kind"] == "estimated_on_mixed_context"
    for state in (before, after):
        assert state["validity"]["traffic_count_balanced"]
        assert state["validity"]["swmm_balance_passed"]
        assert any(f["properties"].get("simulated") for f in state["traffic"]["network"]["features"])
        for feature in state["traffic"]["network"]["features"]:
            assert shape(feature["geometry"]).bounds[0] > 100  # WGS84, not SUMO XY.
    rerun = client.post(f"/api/v1/scenarios/integrated/{result['id']}/recommendations", json={"allow_storage": False, "allow_surface_changes": False})
    assert rerun.status_code == 201, rerun.text
    assert rerun.json()["context"] == result["context"]
    assert rerun.json()["recommendations"][0]["predicted"]["traffic"]["peak_hour_local"] == after["traffic"]["peak_hour_local"]
