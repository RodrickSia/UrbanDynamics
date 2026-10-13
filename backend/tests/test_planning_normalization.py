from copy import deepcopy
import io
import json
import zipfile
from itertools import combinations

import pytest

from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study


def test_declared_program_ratios_use_active_program_and_preserve_totals():
    payload = demo_study()
    payload["comparison_policy"] = "declared_programs"
    payload["normalization_bases"] = ["housing_units", "residents", "floor_area_m2"]
    payload["projects"][1]["development"]["buildings"][0].update(units=100, residents=300)
    original = deepcopy(payload)
    result = run_screening(PlanningStudy(**payload))
    assert original == payload
    options = {o["id"]: o for o in result["options"]}
    assert options["B_only"]["declared_program"]["values"]["housing_units"] == 100
    assert options["B_only"]["declared_program"]["values"]["residents"] == 300
    assert options["A_only"]["declared_program"]["values"]["housing_units"] == 200
    for option in options.values():
        raw = {row["metric"]: row for row in option["comparison"]}
        for row in option["normalized_comparison"]:
            assert row["numerator"] == raw[row["metric"]]["delta"]
            assert row["value"] == pytest.approx(row["numerator"]/row["denominator"])
            assert row["comparability"] == "scenario_only"
            assert row["source_ids"] and row["context_hash"] == result["context"]["sha256"]
    payload["normalization_bases"].reverse()
    assert build_context(PlanningStudy(**payload)) == result["context"]


def test_mixed_school_housing_and_zero_denominator_are_not_normalized_as_homes():
    payload = demo_study("cumulative")
    payload["normalization_bases"] = ["housing_units", "school_places", "floor_area_m2"]
    result = run_screening(PlanningStudy(**payload))
    options = {o["id"]: o for o in result["options"]}
    rows = options["ABC"]["normalized_comparison"]
    assert all(r["value"] is None and r["comparability"] == "not_comparable"
               for r in rows if r["normalization_basis"] in ("housing_units", "school_places"))
    assert all(r["value"] is not None for r in rows if r["normalization_basis"] == "floor_area_m2")
    school = options["B_only"]["declared_program"]["values"]
    assert school["school_places"] == 600 and school["housing_units"] == 0
    payload = demo_study()
    payload["comparison_policy"] = "declared_programs"
    payload["normalization_bases"] = ["housing_units"]
    payload["projects"][0]["development"]["buildings"][0]["units"] = 0
    result = run_screening(PlanningStudy(**payload))
    zero = next(o for o in result["options"] if o["id"] == "A_only")
    assert all(r["value"] is None and r["comparability"] == "insufficient_data" for r in zero["normalized_comparison"])


def test_unknown_baseline_cannot_produce_certain_pressure_ratios():
    payload = demo_study()
    payload["projects"][0]["baseline_occupancy"] = "unknown"
    result = run_screening(PlanningStudy(**payload))
    for option in result["options"]:
        row = next(r for r in option["normalized_comparison"] if r["metric"] == "freshwater_m3_day")
        assert row["value"] is None and row["comparability"] == "insufficient_data"


def test_all_eight_states_and_phase_match_without_accumulating_previous_load():
    payload = demo_study("cumulative")
    payload["options"] = [{"id": "state_"+("".join(ids) or "empty"), "title": "Test subset", "active_project_ids": list(ids)}
                          for count in range(4) for ids in combinations("ABC", count)]
    payload["normalization_bases"] = ["floor_area_m2"]
    result = run_screening(PlanningStudy(**payload))
    assert result["unique_states_evaluated"] == 8
    options = {tuple(o["state"]["active_project_ids"]): o for o in result["options"]}
    assert options[()]["state"] == result["baseline"]
    assert all(r["value"] is None for r in options[()]["normalized_comparison"])
    for phase in result["phases"]:
        same = options[tuple(phase["state"]["active_project_ids"])]
        assert phase["state"] == same["state"]
        assert phase["normalized_comparison"] == same["normalized_comparison"]
    payload["options"].reverse()
    for option in payload["options"]:
        option["active_project_ids"].reverse()
    assert run_screening(PlanningStudy(**payload)) == result


def test_normalization_export_api_includes_program_and_ratios(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.simulation.planning.jobs import process_one
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"store.sqlite"))
    client = TestClient(app)
    saved = client.post("/api/v1/planning/studies", json=demo_study()).json()
    response = client.post(f"/api/v1/planning/studies/{saved['id']}/runs",
                           json={"mode": "screening", "idempotency_key": "normalized-export"})
    assert response.status_code == 202
    completed = process_one()
    assert completed["status"] == "succeeded"
    response = client.get(f"/api/v1/planning/runs/{completed['result_id']}/artifacts")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "normalized-comparison.csv" in archive.namelist()
        programs = json.loads(archive.read("declared-programs.json"))
        assert len(programs) == 3
        assert programs[0]["program"]["values"]["housing_units"] == 200
