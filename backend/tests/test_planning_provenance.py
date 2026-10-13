from copy import deepcopy
import io
import json
import zipfile

import pytest
from shapely.geometry import shape
from xml.etree import ElementTree as ET

from app.services.simulation.planning.context import build_context, preflight
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.map_output import layer
from app.services.simulation.planning.network import specification
from app.services.simulation.planning.native import run_native


def test_manifest_frozen_hashes_temporal_limits_and_source_change():
    payload = demo_study()
    study = PlanningStudy(**payload)
    first = build_context(study)
    manifest = first["source_manifest"]
    entries = {source["id"]: source for source in manifest["entries"]}
    assert all(len(e["payload_sha256"]) == 64 and e["observed_at"] is None and e["source_kind"] == "synthetic" for e in entries.values())
    assert len(manifest["sha256"]) == 64 and manifest["id"] == first["snapshot_manifest_id"]
    # Equivalent collections and serialized input round trips preserve sources.
    payload["projects"].reverse()
    assert build_context(PlanningStudy(**payload)) == first
    assert build_context(PlanningStudy(**first["inputs"])) == first
    payload["utility_zones"][0]["power_capacity_kw"] = 501
    other = build_context(PlanningStudy(**payload))
    other_entries = {e["id"]: e for e in other["source_manifest"]["entries"]}
    assert entries["utility_zones"]["payload_sha256"] != other_entries["utility_zones"]["payload_sha256"]
    assert entries["traffic_network"]["payload_sha256"] == other_entries["traffic_network"]["payload_sha256"]
    assert other["sha256"] != first["sha256"]
    modules = first["data_coverage"]["modules"]
    assert modules["drainage"]["background_area_has_surveyed_polygon"] is False
    assert modules["utilities"]["service_boundary_polygons_available"] is False
    assert modules["shadow"]["neighbouring_inventory_beyond_declared_parcels"] is False


def test_generated_coverage_contains_actual_routes_and_catches_outside_aoi():
    study = PlanningStudy(**demo_study())
    result = run_screening(study)
    modules = result["context"]["data_coverage"]["modules"]
    assert all(shape(modules["traffic"]["geometry"]).covers(shape(f["geometry"])) for f in specification(study)["map"]["features"])
    for option in result["options"]:
        assert all(shape(modules["school"]["geometry"]).buffer(1e-10).covers(shape(f["geometry"])) for f in option["state"]["school_services"]["map"]["features"])
    payload = demo_study()
    payload["projects"], payload["options"] = payload["projects"][:1], payload["options"][:1]
    payload["school_facilities"] = payload["background_school_groups"] = []
    payload["study_area"] = deepcopy(payload["projects"][0]["site"])
    ready = preflight(PlanningStudy(**payload))
    assert ready["context"]["data_coverage"]["modules"]["traffic"]["inside_study_area"] is False
    assert any("extends beyond" in warning for warning in ready["warnings"])


def test_map_feature_sources_units_and_zip_manifest(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.simulation.planning.jobs import process_one
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"sources.sqlite"))
    client = TestClient(app)
    response = client.post("/api/v1/planning/studies", json=demo_study())
    assert response.status_code == 201, response.text
    saved = response.json()
    client.post(f"/api/v1/planning/studies/{saved['id']}/runs", json={"mode": "screening", "idempotency_key": "manifest-zip"})
    job = process_one()
    assert job["status"] == "succeeded", job
    result = client.get(f"/api/v1/planning/runs/{job['result_id']}").json()
    before = deepcopy(result)
    source_ids = {e["id"] for e in result["context"]["source_manifest"]["entries"]}
    for name in ("parcels", "school", "shadow"):
        collection = layer(result, "A_only", name, hour=9)
        assert collection["source_manifest_id"] == result["context"]["snapshot_manifest_id"]
        assert collection["module_coverage"]["observed_coverage"] is False
        for feature in collection["features"]:
            properties = feature["properties"]
            assert properties["source_object_id"] and properties["units"]
            assert set(properties["source_ids"]) <= source_ids
            assert properties["coverage_status"] == "synthetic_scenario_only"
        if collection["features"]:
            collection["features"][0]["properties"]["source_ids"].append("consumer_annotation")
            collection["features"][0]["properties"]["units"]["consumer_annotation"] = "example"
    assert result == before  # Fetching a layer must not mutate the immutable run.
    for option in result["options"]:
        assert all(row["source_manifest_id"] and set(row["source_ids"]) <= source_ids for row in option["comparison"])
    response = client.get(f"/api/v1/planning/runs/{job['result_id']}/artifacts")
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert json.loads(archive.read("source-manifest.json")) == result["context"]["source_manifest"]
        import csv
        rows = list(csv.DictReader(io.StringIO(archive.read("comparison.csv").decode("utf-8-sig"))))
        assert all(row["method"] and row["source_manifest_id"] and json.loads(row["source_ids"]) and row["time_window"] for row in rows)


def test_native_spec_matches_solver_and_rename_preserves_numeric_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path))
    payload = demo_study()
    payload["projects"], payload["options"] = payload["projects"][:1], payload["options"][:1]
    payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    study = PlanningStudy(**payload)
    first = run_native(study)
    spec = specification(study)
    actual = ET.parse(tmp_path/first["network_artifacts"]["artifact_id"]/"edges.xml").getroot()
    assert [edge.attrib for edge in actual] == [{key: str(value) for key, value in edge.items()} for edge in spec["edges"]]
    payload["projects"][0]["id"] = "Renamed"
    payload["options"][0]["active_project_ids"] = ["Renamed"]
    second = run_native(PlanningStudy(**payload))
    for a, b in ((first["baseline"], second["baseline"]), (first["options"][0]["state"], second["options"][0]["state"])):
        left, right = a["traffic"]["runs"][0], b["traffic"]["runs"][0]
        for key in ("planned_vehicles", "completed_vehicles", "mean_completed_delay_seconds", "background_completed_delay_seconds", "max_queue_length_m"):
            assert left[key] == pytest.approx(right[key], abs=1e-6), key
        for name in ("roads", "drainage"):
            collection = layer({**first, "id": "test", "study_id": "test"}, "A_only", name, hour=18)
            assert all(feature["properties"]["units"] and feature["properties"]["source_ids"] for feature in collection["features"])


def test_native_cohorts_with_embedded_separator_ids_do_not_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path))
    payload = demo_study("cumulative")
    payload["projects"] = [payload["projects"][0], {**payload["projects"][2], "id": "A_car__x"}]
    payload["options"] = [{"id": "both", "title": "Namespace conservation", "active_project_ids": ["A", "A_car__x"]}]
    payload["phases"] = []
    payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    result = run_native(PlanningStudy(**payload))
    traffic = result["options"][0]["state"]["traffic"]["runs"][0]
    assert sum(group["planned"] for group in traffic["cohorts"].values()) == traffic["planned_vehicles"]
    assert sum(group["departed"] for group in traffic["cohorts"].values()) == traffic["departed_vehicles"]
    assert sum(group["completed"] for group in traffic["cohorts"].values()) == traffic["completed_vehicles"]
    assert all(group["completed"] <= group["departed"] <= group["planned"] for group in traffic["cohorts"].values())
