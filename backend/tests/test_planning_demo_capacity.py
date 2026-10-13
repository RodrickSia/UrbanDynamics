import copy

import pytest

from app.services.simulation.integrated.background import publish
from app.services.simulation.planning import background, system_demo
from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import rectangle
from app.services.simulation.planning.uncertainty import effective_studies


@pytest.fixture
def snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SYSTEM_DEMO_ENABLED", "1")
    monkeypatch.setenv("PLANNING_SYSTEM_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("PLANNING_COUNTING_REFERENCE_DIR", str(tmp_path / "counting"))
    doc = {"schema_version": 1, "captured_at": "2026-10-13T00:00:00Z",
           "bbox": [106.75, 10.81, 106.77, 10.83], "sources": {},
           "parcels": {"features": [{"type": "Feature", "id": 1, "properties": {}, "geometry": rectangle(106.758, 10.82)}]},
           "population": {"statistics": {"population_sum": 2500}}, "layers": {}, "osm": {"elements": []}}
    return publish(doc, tmp_path)


def prepare(snapshot, **kwargs):
    return PlanningStudy(**system_demo.prepare(system_demo.Prepare(snapshot_id=snapshot, parcel_ids=["1"], **kwargs)))


def test_real_mode_keeps_unknown_and_opt_in_changes_only_fictional_demand(snapshot):
    real = prepare(snapshot)
    fictional = prepare(snapshot, background_mode="synthetic_capacity_v1")
    assert real.projects[0].baseline_occupancy == "unknown"
    assert real.utility_zones[0].water_capacity_m3_day is None
    assert background.resolve(real)["normalization"]["status"] == "inclusive_population_prior_unresolved"
    resolved = background.resolve(fictional)
    assert resolved["residents"] == 1200
    assert resolved["normalization"]["status"] != "inclusive_population_prior_unresolved"
    assert fictional.projects[0].site == real.projects[0].site
    assert fictional.projects[0].baseline_kind == "synthetic"
    context = build_context(fictional)
    assert context["system_background"]["capacity_package"]["source_kind"] == "synthetic"
    sources = {s["id"]: s for s in context["source_manifest"]["entries"]}
    assert sources["regional_population"]["source_kind"] == "synthetic"
    assert sources["utility_zones"]["source_kind"] == "synthetic"


def test_capacity_and_baseline_independent_of_proposal_and_no_mutation(snapshot):
    from app.services.simulation.planning.demo_capacity import apply_package
    source = prepare(snapshot).model_dump(mode="json")
    original = copy.deepcopy(source)
    apply_package(source)
    assert source == original
    small = prepare(snapshot, background_mode="synthetic_capacity_v1", residents=60)
    large = prepare(snapshot, background_mode="synthetic_capacity_v1", residents=600)
    assert small.utility_zones == large.utility_zones
    assert small.background_snapshot == large.background_snapshot
    assert small.school_facilities == large.school_facilities
    result = run_screening(small)
    row = next(r for r in result["options"][0]["comparison"] if r["metric"] == "freshwater_m3_day")
    assert row["before"] is not None and row["after"] is not None
    large_result = run_screening(large)
    assert any(c["status"] == "exceeds_capacity" for z in large_result["options"][0]["state"]["utility_zones"] for c in z["checks"])


def test_existing_building_occupancy_is_hashed_and_subtracted_once(snapshot):
    from app.services.simulation.planning.demo_capacity import apply_package
    source = prepare(snapshot).model_dump(mode="json")
    source["projects"][0]["baseline"] = copy.deepcopy(source["projects"][0]["development"])
    fictional = PlanningStudy(**apply_package(source))
    residents = sum(b.residents for b in fictional.projects[0].baseline.buildings)
    assert residents > 0
    assert fictional.background_residents == 1200 + residents
    assert background.resolve(fictional)["residents"] == 1200


def test_sensitivity_changes_capacity_and_traffic_without_changing_plans(snapshot):
    study = prepare(snapshot, background_mode="synthetic_capacity_v1", sensitivity=True, traffic_peak_vehicles_hour=400)
    cases = {identifier: case for identifier, source, changes, case in effective_studies(study)}
    assert study.uncertainty.seeds == [2026, 2027, 2028]
    assert cases["capacity_minus20"].utility_zones[0].water_capacity_m3_day == 128
    assert cases["capacity_minus20"].school_facilities[0].capacity_places == 192
    assert cases["traffic_half"].background_vehicles_hour == 200
    assert cases["traffic_plus25"].background_vehicles_hour == 500
    for case in cases.values():
        assert case.projects == study.projects
        assert background.resolve(case)["residents"] == 1200


def test_baseline_hash_mismatch_is_rejected(snapshot):
    study = prepare(snapshot, background_mode="synthetic_capacity_v1")
    study.background_snapshot.parcels[0].baseline_sha256 = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        background.resolve(study)


def test_context_survives_canonical_persistence_with_multiple_schools(snapshot):
    from app.services.simulation.planning.context import canonical_input
    study = prepare(snapshot, background_mode="synthetic_capacity_v1", sensitivity=True)
    school = study.school_facilities[0]
    study.school_facilities = [school.model_copy(update={"id": "Z_school"}), school.model_copy(update={"id": "A_school"})]
    context = build_context(study)
    restored = PlanningStudy(**canonical_input(study))
    assert build_context(restored)["sha256"] == context["sha256"]
