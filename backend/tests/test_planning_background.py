from copy import deepcopy

import pytest

from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import rehousing_study
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.background import resolve


def inclusive_case():
    from app.services.simulation.planning.presets import inclusive_rehousing_study
    return PlanningStudy(**rehousing_study()).model_dump(mode="json"), inclusive_rehousing_study()


def test_api_zip_preserves_raw_snapshot_and_normalized_context(tmp_path, monkeypatch):
    import io
    import json
    import zipfile
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.simulation.planning.jobs import process_one
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"snapshot.sqlite"))
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path/"solvers"))
    client = TestClient(app)
    _, payload = inclusive_case()
    response = client.post("/api/v1/planning/studies", json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    response = client.post(f"/api/v1/planning/studies/{saved['id']}/runs",
                           json={"mode": "screening", "idempotency_key": "snapshot-export"})
    assert response.status_code == 202, response.text
    job = process_one()
    assert job["status"] == "succeeded", job
    response = client.get(f"/api/v1/planning/runs/{job['result_id']}/artifacts")
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        raw = json.loads(archive.read("study.json"))
        result = json.loads(archive.read("result.json"))
        sources = json.loads(archive.read("source-manifest.json"))
    assert raw["background_residents"] == 1300
    assert raw["background_snapshot"] == saved["inputs"]["background_snapshot"]
    assert result["context"]["resolved_background"]["residents"] == 1200
    assert result["baseline"]["baseline_ledger"]["background_normalization"]["snapshot_id"] == payload["background_snapshot"]["id"]
    assert sources == result["context"]["source_manifest"]


def test_inclusive_background_matches_clean_states_without_mutating_inputs():
    clean, inclusive = inclusive_case()
    original = deepcopy(inclusive)
    first, second = run_screening(PlanningStudy(**clean)), run_screening(PlanningStudy(**inclusive))
    assert original == inclusive
    assert second["inputs"]["background_residents"] == 1300
    assert second["context"]["resolved_background"]["residents"] == 1200
    assert second["context"]["resolved_background"]["traffic"] == first["context"]["resolved_background"]["traffic"]
    for a,b in zip([first["baseline"]]+[o["state"] for o in first["options"]+first["phases"]],
                   [second["baseline"]]+[o["state"] for o in second["options"]+second["phases"]]):
        for key, value in a["metrics"].items():
            assert b["metrics"][key] == pytest.approx(value) if value is not None else b["metrics"][key] is None
        assert b["hourly_power_kw"] == pytest.approx(a["hourly_power_kw"])
        assert b["school_services"] == a["school_services"]
    normalization = second["baseline"]["baseline_ledger"]["background_normalization"]
    assert normalization["status"] == "inclusive_snapshot_normalized"
    assert len(normalization["removed_contributions"]) == 1
    assert normalization["original"]["residents"] == 1300
    assert normalization["snapshot_sha256"]


def test_inclusive_snapshot_rejects_stale_missing_overcount_and_coverage():
    _, original = inclusive_case()
    def invalid(edit, pattern):
        payload = deepcopy(original)
        edit(payload)
        with pytest.raises(ValueError, match=pattern):
            PlanningStudy(**payload)
    invalid(lambda p: p["background_snapshot"]["parcels"][0].update(baseline_sha256="0"*64), "baseline hash")
    invalid(lambda p: p["background_snapshot"]["parcels"][0].update(utilities=None), "missing utilities")
    invalid(lambda p: p["utility_zones"][0].update(background_freshwater_m3_day=0), "exceed the regional")
    invalid(lambda p: p["background_snapshot"].update(coverage=p["projects"][0]["site"]), "coverage must contain")
    invalid(lambda p: p["background_snapshot"]["parcels"].append(deepcopy(p["background_snapshot"]["parcels"][0])), "duplicates a physical")
    invalid(lambda p: p["background_snapshot"]["parcels"][0].update(project_id="missing"), "unknown project")
    invalid(lambda p: p["background_snapshot"]["parcels"][0].update(school_group_students={"missing": 10}), "unknown group")
    invalid(lambda p: p["background_snapshot"]["included_modules"].remove("utilities"), "supplies utilities")


def test_snapshot_rejects_duplicate_contributions_via_same_parcel_alternatives():
    _, payload = inclusive_case()
    payload["projects"][1] = {**deepcopy(payload["projects"][0]), "id": "B"}
    payload["options"] = [{"id": key, "title": key, "active_project_ids": [key]} for key in ("A", "B", "C")]
    payload["phases"] = []
    payload["background_snapshot"]["parcels"].append({**deepcopy(payload["background_snapshot"]["parcels"][0]), "project_id": "B"})
    with pytest.raises(ValueError, match="duplicates a physical parcel"):
        PlanningStudy(**payload)


def test_snapshot_order_reload_and_sensitivity_use_resolved_traffic():
    from app.services.simulation.planning.uncertainty import effective_studies
    _, inclusive = inclusive_case()
    first = build_context(PlanningStudy(**inclusive))
    inclusive["background_snapshot"]["included_modules"].reverse()
    assert build_context(PlanningStudy(**inclusive)) == first
    assert build_context(PlanningStudy(**first["inputs"])) == first
    inclusive["uncertainty"] = {"engine": "screening", "cases": [{"id": "busy", "source": "Synthetic resolved external flow increase", "background_vehicles_hour": 500}]}
    cases = effective_studies(PlanningStudy(**inclusive))
    assert cases[1][0] == "busy"
    clean = resolve(cases[1][3])
    assert all(a+b == 500 for a,b in zip(clean["traffic"]["cars"], clean["traffic"]["motorcycles"]))
    assert clean["residents"] == 1200


def test_native_inclusive_snapshot_matches_clean_traffic_and_drainage(tmp_path, monkeypatch):
    from app.services.simulation.planning.native import run_native
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path))
    clean, inclusive = inclusive_case()
    for payload in (clean, inclusive):
        payload["projects"] = [payload["projects"][0], payload["projects"][2]]
        payload["options"] = [{"id": "AC", "title": "Shared rehousing portfolio", "active_project_ids": ["A", "C"]}]
        payload["phases"] = []
        payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    a,b = run_native(PlanningStudy(**clean)), run_native(PlanningStudy(**inclusive))
    assert all(a["validity"].values()) and all(b["validity"].values())
    for left,right in ((a["baseline"],b["baseline"]), (a["options"][0]["state"],b["options"][0]["state"])):
        for key in ("planned_vehicles", "completed_vehicles", "mean_completed_delay_seconds", "max_queue_length_m", "cohorts", "edge_intervals"):
            assert left["traffic"]["runs"][0][key] == right["traffic"]["runs"][0][key]
        assert left["drainage"]["catchments"][0]["node_flooding_m3"] == pytest.approx(right["drainage"]["catchments"][0]["node_flooding_m3"], abs=.01)
