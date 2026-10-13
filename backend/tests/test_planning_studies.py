import copy
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.simulation.planning.context import build_context, preflight
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.jobs import process_one
from app.services.simulation.planning.models import PlanningStudy, UtilityZone
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.utilities import aggregate
from app.services.simulation.planning import store


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"planning.sqlite"))


def test_equal_program_rejects_reduced_units_and_geometry_outside_region():
    payload = demo_study()
    payload["projects"][1]["development"]["buildings"][0]["units"] = 150
    with pytest.raises(ValueError, match="equal-program target housing_units"):
        PlanningStudy(**payload)
    payload = demo_study()
    payload["study_area"] = copy.deepcopy(payload["projects"][0]["site"])
    with pytest.raises(ValueError, match="outside the study"):
        PlanningStudy(**payload)


def test_invalid_ids_phases_and_overlapping_active_parcels_rejected():
    payload = demo_study("cumulative")
    payload["options"][0]["active_project_ids"] = ["missing"]
    with pytest.raises(ValueError, match="Unknown project"):
        PlanningStudy(**payload)
    payload = demo_study("cumulative")
    payload["phases"][1]["active_project_ids"] = ["B"]
    with pytest.raises(ValueError, match="retain previously"):
        PlanningStudy(**payload)
    payload = demo_study("cumulative")
    payload["projects"][1] = {**copy.deepcopy(payload["projects"][0]), "id": "B"}
    with pytest.raises(ValueError, match="Overlapping"):
        PlanningStudy(**payload)


def test_frozen_context_and_results_independent_of_collection_order():
    payload = demo_study("cumulative")
    original = copy.deepcopy(payload)
    first = PlanningStudy(**payload)
    payload["projects"].reverse()
    payload["options"].reverse()
    payload["phases"].reverse()
    for option in payload["options"]+payload["phases"]:
        option["active_project_ids"].reverse()
    second = PlanningStudy(**payload)
    assert build_context(first) == build_context(second)
    assert run_screening(first) == run_screening(second)
    assert first.model_dump(mode="json")["projects"][0]["baseline"] == PlanningStudy(**original).model_dump(mode="json")["projects"][0]["baseline"]


def test_shared_capacity_peak_of_sum_and_not_sum_of_peaks():
    zone = UtilityZone(id="shared", source="Synthetic isolated load test", power_capacity_kw=12)
    loads = []
    for hour in (7, 18):
        profile = [0]*24
        profile[hour] = 10
        loads.append({"utility_zone_id": "shared", "demand": {"hourly": {"power_kw": profile}, "freshwater_m3_day": 5, "wastewater_m3_day": 4}})
    combined = aggregate([zone], loads)[0]
    assert combined["metrics"]["power_peak_kw"] == 10
    assert combined["checks"][0]["status"] == "within_capacity"
    assert combined["metrics"]["freshwater_m3_day"] == 10
    loads[1]["demand"]["hourly"]["power_kw"] = loads[0]["demand"]["hourly"]["power_kw"][:]
    assert aggregate([zone], loads)[0]["checks"][0]["status"] == "exceeds_capacity"


def test_missing_capacity_and_unknown_occupancy_never_approve_capacity():
    payload = demo_study()
    payload["utility_zones"][0]["water_capacity_m3_day"] = None
    payload["projects"][0]["baseline_occupancy"] = "unknown"
    study = PlanningStudy(**payload)
    result = run_screening(study)
    assert preflight(study)["baseline_unknown_occupancy_projects"] == ["A"]
    assert all(check["status"] == "unknown" for check in result["options"][0]["state"]["utility_zones"][0]["checks"])
    row = next(row for row in result["options"][0]["comparison"] if row["metric"] == "freshwater_m3_day")
    assert row["comparability"] == "insufficient_data"
    assert row["before"] is row["after"] is row["delta"] is None
    assert row["scenario_values"]["before"] is not None
    assert row["unavailable_reason"]


def test_portfolio_baseline_ledger_unique_states_and_phase_equivalence():
    result = run_screening(PlanningStudy(**demo_study("cumulative")))
    assert result["baseline"]["metrics"]["residents"] == 1200
    assert result["unique_states_evaluated"] == 6  # baseline, three singles, AB, ABC; phases reuse states
    options = {x["id"]: x for x in result["options"]}
    assert options["ABC"]["state"]["metrics"]["residents"] == 2250  # visitors/students not permanent residents
    assert result["phases"][1]["state"] == options["AB"]["state"]
    assert result["phases"][2]["state"] == options["ABC"]["state"]
    assert options["ABC"]["state"]["utility_zones"][0]["checks"][0]["status"] == "exceeds_capacity"
    assert options["A_only"]["state"]["utility_zones"][0]["checks"][0]["status"] == "within_capacity"
    for row in result["marginal_effects"][1]["rows"]:
        assert row["before"] == result["phases"][0]["state"]["metrics"][row["metric"]]


def test_same_parcel_alternatives_do_not_duplicate_baseline():
    payload = demo_study()
    payload["projects"] = [payload["projects"][0], {**copy.deepcopy(payload["projects"][0]), "id": "B"}]
    payload["projects"][1]["site"]["coordinates"][0].reverse()
    payload["options"] = payload["options"][:2]
    result = run_screening(PlanningStudy(**payload))
    assert len(result["baseline"]["parcels"]) == 1
    assert len(result["options"][0]["state"]["parcels"]) == 1
    assert result["options"][0]["state"]["metrics"] == result["options"][1]["state"]["metrics"]


def test_same_parcel_conflicting_access_lanes_rejected():
    payload = demo_study()
    payload["projects"] = [payload["projects"][0], {**copy.deepcopy(payload["projects"][0]), "id": "B"}]
    payload["options"] = payload["options"][:2]
    payload["projects"][1]["development"]["gate_lanes"] = 2
    with pytest.raises(ValueError, match="common physical access"):
        PlanningStudy(**payload)


def test_durable_api_worker_idempotency_revision_and_zip():
    client = TestClient(app)
    payload = demo_study("cumulative")
    ready = client.post("/api/v1/planning/studies/preflight", json=payload)
    assert ready.status_code == 200, ready.text
    created = client.post("/api/v1/planning/studies", json=payload)
    assert created.status_code == 201, created.text
    study_id = created.json()["id"]
    request = {"mode": "screening", "idempotency_key": "portfolio-screening-001"}
    queued = client.post(f"/api/v1/planning/studies/{study_id}/runs", json=request)
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "queued"
    assert client.post(f"/api/v1/planning/studies/{study_id}/runs", json=request).json()["id"] == queued.json()["id"]
    complete = process_one()
    assert complete["status"] == "succeeded", complete
    assert process_one() is None
    stored = client.get(f"/api/v1/planning/jobs/{complete['id']}").json()
    assert stored["result_id"] == complete["result_id"]
    result = client.get(f"/api/v1/planning/runs/{complete['result_id']}")
    assert result.status_code == 200
    assert result.json()["context"]["sha256"] == ready.json()["context_hash"]
    mapped = client.get(f"/api/v1/planning/runs/{complete['result_id']}/map", params={"option_id": "phase_3", "name": "school"})
    assert mapped.status_code == 200
    assert mapped.json()["features"]
    assert all(f["properties"]["study_id"] == study_id and f["properties"]["phase_id"] == "phase_3" for f in mapped.json()["features"])
    assert client.get(f"/api/v1/planning/runs/{complete['result_id']}/map", params={"option_id": "ABC", "name": "roads"}).status_code == 409
    assert client.get(f"/api/v1/planning/runs/{complete['result_id']}/map", params={"option_id": "unknown"}).status_code == 422
    archive = client.get(f"/api/v1/planning/runs/{complete['result_id']}/artifacts")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        assert bundle.testzip() is None
        assert json.loads(bundle.read("result.json")) == result.json()
        assert "comparison.csv" in bundle.namelist()
        assert "maps/ABC/school.geojson" in bundle.namelist()
    payload["title"] = "Updated scenario revision"
    revision = client.post(f"/api/v1/planning/studies/{study_id}/revisions", json=payload)
    assert revision.status_code == 201
    assert revision.json()["parent_revision_id"] == study_id
    assert client.get(f"/api/v1/planning/studies/{study_id}").json() == created.json()


def test_cancel_queued_and_running_job_does_not_publish_result():
    study = PlanningStudy(**demo_study())
    context = build_context(study)
    saved = store.save_study(context["inputs"], context["sha256"])
    first = store.enqueue(saved["id"], "screening", "cancel-queued")
    assert store.cancel(first["id"])["status"] == "cancelled"
    assert process_one() is None
    second = store.enqueue(saved["id"], "screening", "cancel-running")
    owner = store.claim()
    assert owner["id"] == second["id"]
    store.cancel(second["id"])
    assert not store.heartbeat(owner, {"done": 1})
    ended = store.finish(owner, result={"should_not_publish": True})
    assert ended["status"] == "cancelled" and ended["result_id"] is None


def test_screening_does_not_claim_native_metrics():
    client = TestClient(app)
    created = client.post("/api/v1/planning/studies", json=demo_study()).json()
    assert client.post(f"/api/v1/planning/studies/{created['id']}/runs", json={"mode": "native", "idempotency_key": "native-ready"}).status_code == 202
    result = run_screening(PlanningStudy(**demo_study()))
    assert result["baseline"]["native_simulation"] is False
    assert "traffic_delay_seconds" not in result["baseline"]["metrics"]
