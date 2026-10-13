from copy import deepcopy
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.simulation.planning.context import canonical_input, build_context, preflight
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.uncertainty import effective_studies, run, spread, ranking_stability, seed_summary
from app.services.simulation.planning.jobs import process_one


def study_payload(engine="screening"):
    payload = demo_study()
    payload["conditions"] = {"traffic_hours": [18]}
    payload["criteria"] = [{"metric": "power_peak_kw", "direction": "minimize", "weight": 1},
                           {"metric": "school_unserved_students", "direction": "minimize", "weight": 2}]
    payload["uncertainty"] = {"engine": engine, "seeds": [2026, 2027, 2028], "cases": [
        {"id": "low", "source": "Synthetic low demand case", "level": "low"},
        {"id": "high", "source": "Synthetic high demand case", "level": "high"},
        {"id": "capacity", "source": "Synthetic lower shared utility capacity", "utility_capacity_scale": .8}]}
    return payload


def test_case_inputs_frozen_programs_preserved_unknown_capacity_and_validated_preflight():
    payload = study_payload()
    payload["utility_zones"][0]["water_capacity_m3_day"] = None
    study = PlanningStudy(**payload)
    original = canonical_input(study)
    cases = effective_studies(study)
    assert [c[0] for c in cases] == ["reference", "capacity", "high", "low"]
    for _, _, _, case in cases:
        assert case.projects == study.projects
        assert case.program_targets == study.program_targets
        assert case.utility_zones[0].water_capacity_m3_day is None
        assert case.conditions.seeds == [2026, 2027, 2028]
    assert canonical_input(study) == original
    assert preflight(study)["uncertainty_work_estimate"]["sumo_runs"] == 0
    payload["uncertainty"]["cases"] = [{"id": "impossible", "source": "Too few school places for reserved users", "existing_school_capacity_scale": .01}]
    with pytest.raises(ValueError, match="Reserved school"):
        preflight(PlanningStudy(**payload))


def test_spread_and_ranking_do_not_promote_one_seed_missing_values_or_arbitrary_ties():
    assert spread([1], 1, .5)["delta_stability"] == "insufficient_seed_suite"
    assert spread([1, None, 3], 3, .5)["delta_stability"] == "insufficient_data"
    assert spread([-.1, .2, .3], 3, .5)["delta_stability"] == "within_material_threshold"
    assert spread([1, 2, -3], 3, .5)["delta_stability"] == "changes_sign_or_crosses_material_threshold"
    sample = {"status": "scenario_only", "pareto_option_ids": ["A", "B"], "weighted_scores": [
        {"option_id": "B", "score": .5}, {"option_id": "A", "score": .5}]}
    assert ranking_stability([{"ranking": sample}], minimum_count=3)["status"] == "insufficient_samples"
    swapped = deepcopy(sample)
    swapped["weighted_scores"].reverse()
    assert ranking_stability([{"ranking": sample}, {"ranking": swapped}])["weighted_top_set_stable"]


def test_screening_assumptions_saved_with_separate_request_effective_inputs_and_weight_cases():
    study = PlanningStudy(**study_payload())
    result = run(study)
    assert result["analysis_request_context_hash"] == build_context(study)["sha256"]
    assert result["context"]["inputs"]["conditions"]["seeds"] == [2026, 2027, 2028]
    assert result["analysis_request"]["conditions"]["seeds"] == [2026]
    assert all(c["result"]["inputs"]["projects"] == result["inputs"]["projects"] for c in result["assumption_cases"])
    assert len(result["uncertainty_analysis"]["weights"]["samples"]) == 5
    assert any(r["metric"] == "power_peak_kw" and r["status"] == "sensitive_in_sampled_cases" for r in result["uncertainty_analysis"]["capacity_stability"])
    assert all(r["status"] == "insufficient_data" for r in result["uncertainty_analysis"]["traffic_case_mean_ranges"])
    reordered = study_payload()
    reordered["uncertainty"]["cases"].reverse()
    reordered["uncertainty"]["seeds"].reverse()
    assert build_context(PlanningStudy(**reordered)) == build_context(study)


def test_uncertainty_api_worker_map_case_and_zip_request(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"uncertainty.sqlite"))
    client = TestClient(app)
    missing = client.post("/api/v1/planning/studies", json=demo_study()).json()
    assert client.post(f"/api/v1/planning/studies/{missing['id']}/runs", json={"mode": "uncertainty", "idempotency_key": "no-settings"}).status_code == 422
    study = client.post("/api/v1/planning/studies", json=study_payload()).json()
    job = client.post(f"/api/v1/planning/studies/{study['id']}/runs", json={"mode": "uncertainty", "idempotency_key": "declared-cases"})
    assert job.status_code == 202
    done = process_one()
    assert done["status"] == "succeeded"
    result = client.get(f"/api/v1/planning/runs/{done['result_id']}").json()
    assert result["analysis_request_context_hash"] == study["context_hash"]
    mapped = client.get(f"/api/v1/planning/runs/{done['result_id']}/map", params={"name": "school", "option_id": "A_only", "case_id": "low"})
    assert mapped.status_code == 200
    assert mapped.json()["context_hash"] == next(c["context_hash"] for c in result["assumption_cases"] if c["id"] == "low")
    assert all(f["properties"]["study_id"] == study["id"] and f["properties"]["assumption_case_id"] == "low" for f in mapped.json()["features"])
    archive = client.get(f"/api/v1/planning/runs/{done['result_id']}/artifacts")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        assert bundle.testzip() is None
        assert "analysis-request.json" in bundle.namelist()
        assert "cases/low/input.json" in bundle.namelist()
        assert "cases/low/result.json" in bundle.namelist()
        assert "capacity" in bundle.read("comparison.csv").decode("utf-8-sig")


def test_counting_prior_sensitivity_scales_effective_profile_and_preserves_mix():
    from app.services.simulation.planning.background import resolve
    payload = study_payload()
    payload["traffic_prior"] = {"cars": [50]*24, "motorcycles": [750]*24,
                               "source": "Historical unmapped vehicle-mix prior; peak amplitude assumed"}
    payload["traffic_prior"]["cars"][0] = 5
    payload["traffic_prior"]["motorcycles"][0] = 75
    payload["uncertainty"]["cases"] = [{"id":"traffic_low", "source":"Assumed lower peak", "background_vehicles_hour":400},
                                         {"id":"traffic_high", "source":"Assumed higher peak", "background_vehicles_hour":1200}]
    original = deepcopy(payload)
    cases = {name: case for name,_,_,case in effective_studies(PlanningStudy(**payload))}
    for name,peak in [("reference",800),("traffic_low",400),("traffic_high",1200)]:
        traffic=resolve(cases[name])["traffic"]
        assert traffic["cars"][18]+traffic["motorcycles"][18] == peak
        assert traffic["cars"][0]+traffic["motorcycles"][0] == peak//10
        assert traffic["cars"][18] == peak//16
    assert payload == original
