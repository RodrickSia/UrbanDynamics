from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.simulation.planning import benchmark, store
from app.services.simulation.planning.context import build_context, preflight
from app.services.simulation.planning.jobs import process_one
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path / "studies.sqlite"))
    monkeypatch.setenv("PLANNING_BENCHMARK_MACHINE_ID", "test-worker")


def test_actual_screening_job_publishes_compatible_timing_without_changing_context(monkeypatch):
    study = PlanningStudy(**demo_study())
    context = build_context(study)
    before = preflight(study)
    assert before["runtime_estimates"]["screening"]["status"] == "unavailable"
    saved = store.save_study(context["inputs"], context["sha256"])
    store.enqueue(saved["id"], "screening", "benchmark-screening")
    done = process_one()
    assert done["status"] == "succeeded"
    result = store.load_document(done["result_id"], "run")
    assert result["runtime"]["compute_seconds"] > 0
    assert result["runtime"]["benchmark_eligible"]
    after = preflight(study)
    estimate = after["runtime_estimates"]["screening"]
    assert after["context_hash"] == before["context_hash"] == context["sha256"]
    assert estimate["status"] == "measured_example"
    assert estimate["reference_run_ids"] == [done["result_id"]]
    assert estimate["estimated_compute_seconds"] == result["runtime"]["compute_seconds"]
    renamed = deepcopy(context["inputs"])
    renamed["title"] = "Another review title"
    assert benchmark.profile(PlanningStudy(**renamed), build_context(PlanningStudy(**renamed)), "screening") == benchmark.profile(study, context, "screening")
    changed = deepcopy(context)
    changed["inputs"]["conditions"]["traffic_hours"] = [12]
    assert benchmark.estimate(study, changed, "screening")["status"] == "unavailable"
    monkeypatch.setenv("PLANNING_BENCHMARK_MACHINE_ID", "different-worker")
    assert benchmark.estimate(study, context, "screening")["status"] == "unavailable"


def test_unconfigured_worker_does_not_need_database(monkeypatch):
    monkeypatch.delenv("PLANNING_BENCHMARK_MACHINE_ID")
    monkeypatch.setattr(store, "benchmark_samples", lambda _: pytest.fail("Unexpected database access"))
    study = PlanningStudy(**demo_study())
    assert preflight(study)["runtime_estimates"]["native"]["status"] == "unavailable"


@pytest.mark.parametrize("hits,eligible", [(0, True), (1, False), (5, False)])
def test_cold_native_only_and_engine_version_isolation(hits, eligible):
    study = PlanningStudy(**demo_study())
    context = build_context(study)
    executor = SimpleNamespace(hits=hits, computations=5-hits, versions={"sumo": "test-version"})
    timing = benchmark.measurement(study, context, "native", 12, executor)
    assert timing["benchmark_eligible"] == eligible
    assert benchmark.profile(study, context, "native", executor.versions) != benchmark.profile(study, context, "native", {"sumo": "new-version"})
    changed = {**context, "model_version": "new-model"}
    assert benchmark.profile(study, changed, "native", executor.versions) != benchmark.profile(study, context, "native", executor.versions)


@pytest.mark.parametrize("cancelled", [False, True])
def test_unsuccessful_jobs_publish_no_benchmark(cancelled):
    study = PlanningStudy(**demo_study())
    context = build_context(study)
    saved = store.save_study(context["inputs"], context["sha256"])
    store.enqueue(saved["id"], "screening", "unsuccessful")
    owner = store.claim()
    if cancelled:
        store.cancel(owner["id"])
    store.finish(owner, cancelled=cancelled, error=None if cancelled else "Deliberate failure")
    key = benchmark.profile(study, context, "screening")
    assert store.benchmark_samples(key["sha256"]) == []
