"""Map handoff, geometric effects and frozen native comparisons; fixture data only."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape

from app.main import app
from app.routers.integrated_scenarios import demo_payload
from app.services.simulation.integrated import background, geometry, solvers
from app.services.simulation.integrated.context import build_context
from app.services.simulation.integrated.models import Conditions, Design, IntegratedRequest


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for key in ("WAREHOUSE_PASSWORD", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SIMULATION_SNAPSHOT_DIR", str(tmp_path/"snapshots"))
    monkeypatch.setenv("SCENARIO_DATA_DIR", str(tmp_path/"runs"))
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path/"engines"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path/"data"))


def rectangle(west, south, east, north):
    return {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north],
                                                  [west, north], [west, south]]]}


def fixture_payload():
    return json.loads((Path(__file__).resolve().parents[2]/"docs/samples/simulation-map-context.json").read_text(encoding="utf-8"))


def context(payload=None):
    return build_context(IntegratedRequest(**(payload or fixture_payload())))


def test_raw_source_height_priority_and_baseline_geometry():
    payload = fixture_payload()
    result = context(payload)
    building = result["baseline"]["buildings"][0]
    assert building["height_m"] == 18
    assert building["floors"] == 6
    assert building["use"] == "residential"
    assert building["residents"] == 0  # Map geometry does not provide occupancy.
    record = result["baseline_provenance"]["buildings"][0]
    assert record["height_attribute"] == "max_height"
    assert not record["survey_verified"]
    geometry.analyze(IntegratedRequest(**payload).site, Design(**result["baseline"]))
    assert len(result["surrounding_buildings"]["features"]) == 1
    assert result["data_inventory"]["map_context"]["coverage_complete"] is False


@pytest.mark.parametrize("kind,properties,height,height_kind", [
    ("visual_fallback", {"height": 12}, 3, "synthetic_default"),
    ("unknown", {"height": 12}, 3, "synthetic_default"),
    ("source_attribute", {}, 3, "synthetic_default"),
    ("source_attribute", {"height": 12}, 12, "source_attribute_estimate"),
    ("source_attribute", {"height": 0, "render_height": "24 m"}, 24, "source_attribute_estimate"),
    ("source_attribute", {"building:levels": 5}, 15, "inferred_from_source_floors_3m"),
    ("source_attribute", {"height": True}, 3, "synthetic_default"),
])
def test_height_defaults_are_not_observed(kind, properties, height, height_kind):
    payload = fixture_payload()
    feature = payload["map_context"]["buildings"]["features"][0]
    feature.update(properties=properties, height_kind=kind)
    result = context(payload)
    assert result["baseline"]["buildings"][0]["height_m"] == height
    assert result["baseline_provenance"]["buildings"][0]["height"] == height_kind


def test_duplicate_geometry_and_tile_fragments_are_merged():
    payload = fixture_payload()
    features = payload["map_context"]["buildings"]["features"]
    original = deepcopy(features[0])
    original["id"] = "different-id-same-geometry"
    features.append(original)
    features.append({**deepcopy(features[0]), "geometry": rectangle(106.7604, 10.8201, 106.7606, 10.8204)})
    result = context(payload)
    assert len(result["baseline"]["buildings"]) == 1
    assert shape(result["baseline"]["buildings"][0]["footprint"]).bounds[2] == pytest.approx(106.7606)
    geometry.analyze(IntegratedRequest(**payload).site, Design(**result["baseline"]))


def test_exact_geometry_dedup_and_known_height_beats_unknown():
    payload = fixture_payload()
    features = payload["map_context"]["buildings"]["features"]
    known = deepcopy(features[0])
    features[0].update(properties={"height": 12}, height_kind="visual_fallback")
    known["id"] = "same-shape"
    features.append(known)
    result = context(payload)
    assert len(result["baseline"]["buildings"]) == 1
    assert result["baseline"]["buildings"][0]["height_m"] == 18
    assert result["data_inventory"]["map_context"]["normalized_buildings"] == 2


def test_duplicate_geometry_preserves_source_floors_when_height_arrives():
    payload = fixture_payload()
    features = payload["map_context"]["buildings"]["features"]
    duplicate = deepcopy(features[0])
    features[0]["properties"] = {"building:levels": 5}
    duplicate.update(id="same-geometry-height", properties={"height": 18})
    features.append(duplicate)
    result = context(payload)
    assert result["baseline"]["buildings"][0]["height_m"] == 18
    assert result["baseline"]["buildings"][0]["floors"] == 5
    assert result["baseline_provenance"]["buildings"][0]["floors"] == "source_attribute_estimate"


def test_multipolygon_holes_and_site_boundary_clipping():
    payload = fixture_payload()
    feature = payload["map_context"]["buildings"]["features"][0]
    outer = rectangle(106.7599, 10.8201, 106.7604, 10.8204)["coordinates"]
    outer.append(rectangle(106.7601, 10.8202, 106.7602, 10.8203)["coordinates"][0])
    feature["geometry"] = {"type": "MultiPolygon", "coordinates": [outer,
        rectangle(106.7606, 10.8201, 106.7608, 10.8203)["coordinates"]]}
    result = context(payload)
    assert len(result["baseline"]["buildings"]) == 2
    assert any(len(b["footprint"]["coordinates"]) == 2 for b in result["baseline"]["buildings"])
    geometry.analyze(IntegratedRequest(**payload).site, Design(**result["baseline"]))
    for f in result["surrounding_buildings"]["features"]:
        assert shape(f["geometry"]).intersection(shape(payload["site"])).area < 1e-15


@pytest.mark.parametrize("fault", ["conflicting_height", "duplicate_conflict", "bad_bbox", "timezone", "synthetic", "invalid_geometry", "too_many", "extra_url"])
def test_invalid_map_context_returns_422(fault):
    payload = fixture_payload()
    mapped = payload["map_context"]
    feature = mapped["buildings"]["features"][0]
    if fault in ("conflicting_height", "duplicate_conflict"):
        duplicate = deepcopy(feature)
        duplicate["properties"]["max_height"] = 40
        if fault == "duplicate_conflict":
            duplicate["id"] = "other-id"
        mapped["buildings"]["features"].append(duplicate)
    elif fault == "bad_bbox":
        mapped["bbox"] = [105, 10, 105.1, 10.1]
    elif fault == "timezone":
        mapped["captured_at"] = "2026-10-11T08:00:00"
    elif fault == "synthetic":
        payload["data_mode"] = "synthetic"
    elif fault == "invalid_geometry":
        feature["geometry"]["coordinates"][0][1] = [999, 10]
    elif fault == "too_many":
        mapped["buildings"]["features"] = [feature]*201
    else:
        mapped["source_url"] = "http://localhost/private"
    response = TestClient(app).post("/api/v1/scenarios/integrated/context", json=payload)
    assert response.status_code == 422, response.text


def test_empty_map_is_incomplete_and_user_baseline_overrides():
    payload = fixture_payload()
    payload["map_context"]["buildings"]["features"] = []
    result = context(payload)
    assert not result["baseline_provenance"]["coverage_complete"]
    assert result["baseline_provenance"]["unclassified_surface_m2"] > 0
    payload = fixture_payload()
    payload["baseline"] = {"design": payload["development"], "source": "Team supplied baseline design"}
    result = context(payload)
    assert result["baseline"] == IntegratedRequest(**payload).development.model_dump(mode="json")
    assert result["baseline_provenance"]["kind"] == "user_supplied"
    assert result["surrounding_buildings"]["features"]


def test_explicit_baseline_does_not_require_auto_baseline_under_20_parts():
    payload = fixture_payload()
    features = payload["map_context"]["buildings"]["features"]
    for i in range(21):
        x = 106.76005 + (i % 7)*.00012
        y = 10.82055 + (i // 7)*.00012
        features.append({"type": "Feature", "id": f"dense-{i}",
                         "geometry": rectangle(x, y, x+.00005, y+.00005), "properties": {"height": 6}})
    # Automatic baseline is too complex for this pilot; the explicit one is valid.
    with pytest.raises(ValueError, match="more than 20"):
        context(payload)
    payload["baseline"] = {"design": payload["development"], "source": "Explicit design of the existing site"}
    assert context(payload)["baseline_provenance"]["kind"] == "user_supplied"


def test_snapshot_osm_overlap_uses_map_priority():
    from test_simulation_background import snapshot
    payload = fixture_payload()
    # Put the same footprint in both sources to exercise roof deduplication.
    payload["map_context"]["buildings"]["features"][0]["geometry"] = payload["development"]["buildings"][0]["footprint"]
    payload["snapshot_id"] = background.publish(snapshot())
    result = context(payload)
    assert len(result["baseline"]["buildings"]) == 1
    assert result["baseline"]["buildings"][0]["height_m"] == 18
    assert result["data_inventory"]["coverage"]["building_footprints"] == "client_map_and_osm_incomplete"


def test_neighbour_shadow_changes_site_without_new_design_buildings():
    payload = fixture_payload()
    result = context(payload)
    request = IntegratedRequest(**payload)
    geom = geometry.analyze(request.site, Design(**result["baseline"]))
    without = geometry.shadows(geom, Design(**result["baseline"]), Conditions())
    with_context = geometry.shadows(geom, Design(**result["baseline"]), Conditions(), result["surrounding_buildings"])
    assert with_context["mean_outdoor_shaded_percent"] > without["mean_outdoor_shaded_percent"]
    assert with_context["surrounding_building_count"] == 1


def test_context_preflight_runs_no_solver_and_hash_captures_height(monkeypatch):
    monkeypatch.setattr(solvers, "traffic", lambda *a: pytest.fail("Preflight cannot run SUMO"))
    client = TestClient(app)
    payload = fixture_payload()
    response = client.post("/api/v1/scenarios/integrated/context", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["surrounding_buildings"]["features"]
    payload["map_context"]["buildings"]["features"][1]["properties"]["height"] = 30
    changed = client.post("/api/v1/scenarios/integrated/context", json=payload)
    assert changed.json()["sha256"] != response.json()["sha256"]


def test_native_predict_save_recommend_and_export_keep_map_context():
    client = TestClient(app)
    response = client.post("/api/v1/scenarios/integrated/predict", json=fixture_payload())
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["model_version"] == "integrated-building-1.4"
    for state in result["variants"].values():
        assert all(state["validity"].values())
        assert state["shadow"]["surrounding_buildings"] == result["context"]["surrounding_buildings"]
    assert result["variants"]["baseline"]["buildings_map"]["features"][0]["properties"]["kind"] == "baseline_estimate"
    assert result["variants"]["development"]["buildings_map"]["features"][0]["properties"]["kind"] == "design"
    assert result["assessment"]["rows"][0]["kind"] == "estimated_on_mixed_context"
    identifier = result["id"]
    assert client.get(f"/api/v1/scenarios/integrated/{identifier}").json()["context"] == result["context"]
    rerun = client.post(f"/api/v1/scenarios/integrated/{identifier}/recommendations", json={})
    assert rerun.status_code == 201, rerun.text
    assert rerun.json()["context"] == result["context"]
    assert rerun.json()["recommendations"]
    for candidate in rerun.json()["recommendations"]:
        assert candidate["predicted"]["shadow"]["surrounding_buildings"] == result["context"]["surrounding_buildings"]
    assert client.get(f"/api/v1/scenarios/integrated/{identifier}/artifacts").status_code == 200
