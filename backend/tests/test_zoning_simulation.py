from copy import deepcopy

import pytest
from pydantic import ValidationError

from test_development import building, parcel_source  # noqa: F401
from test_zoning import client, plan, command  # noqa: F401
from app.services.simulation.integrated import demand, geometry
from app.services.simulation.integrated.library import parameters
from app.services.simulation.integrated.models import Building
from app.services.simulation.planning import store
from app.services.simulation.planning.jobs import process_one
from app.services.simulation.planning.models import PlanningStudy


def freeze(client, plan, **settings):
    return client.post(f"/api/v1/zoning/plans/{plan['id']}/simulation/studies", json={
        "revision": plan["revision"], "scenario_id": plan["scenarios"][1]["id"], **settings})


@pytest.mark.parametrize('mode', ['screening', 'native'])
def test_saved_mixed_floors_feed_screening_without_duplicate_geometry(client, plan, parcel_source, tmp_path, monkeypatch, mode):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path / "simulation.sqlite"))
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path / "solvers"))
    plan = command(client, plan, "save_building", building(floors=3, floor_overrides=[
        {"floor": 1, "floor_height": 4, "space_use_id": "commercial", "counts_gfa": False, "counts_far": False},
        {"floor": 2, "floor_height": 3.6, "space_use_id": "office", "counts_gfa": True, "counts_far": True},
    ]))
    original = deepcopy(plan)
    response = freeze(client, plan)
    assert response.status_code == 201, response.text
    saved = store.load_document(response.json()["id"], "study")
    study = PlanningStudy(**saved["inputs"])
    project = study.projects[0]
    block = project.development.buildings[0]
    assert len(project.development.buildings) == 1
    assert {p.use for p in block.space_uses} == {"residential", "office", "other"}
    assert block.height_m == pytest.approx(10.8)
    analysis = geometry.analyze(project.site, project.development)
    roof = analysis["metrics"]["roof_m2"]
    assert block.gross_floor_area_m2 == pytest.approx(roof * 2)
    assert sum(p.floor_area_m2 for p in block.space_uses) == pytest.approx(roof * 3)
    loads = demand.calculate(project.development, analysis["floor_areas"], parameters("base"))
    library = parameters("base")
    expected = sum(p.floor_area_m2*library["uses"][p.use]["energy_kwh_m2_day"] for p in block.space_uses)
    assert loads["energy_kwh_day"] == pytest.approx(expected)
    assert project.baseline_occupancy == "unknown"
    assert study.utility_zones[0].power_capacity_kw is None
    job = client.post(f"/api/v1/planning/studies/{saved['id']}/runs", json={"mode": mode, "idempotency_key": "plan-screening-test"})
    assert job.status_code == 202
    finished = process_one()
    assert finished["status"] == "succeeded", finished
    result = client.get(f"/api/v1/planning/runs/{finished['result_id']}").json()
    assert result["options"][0]["state"]["metrics"]["energy_kwh_day"] == pytest.approx(expected)
    water = next(row for row in result["options"][0]["comparison"] if row["metric"] == "freshwater_m3_day")
    assert water["delta"] is None and water["comparability"] == "insufficient_data"
    assert client.get(f"/api/v1/zoning/plans/{plan['id']}").json() == original
    # Changing the editor afterwards must not mutate the frozen simulation.
    changed = command(client, plan, "save_building", building(id=plan['scenarios'][1]['buildings'][0]['id'], floors=1))
    assert freeze(client, plan).status_code == 409
    assert store.load_document(saved["id"], "study")["inputs"] == saved["inputs"]
    assert changed["revision"] > original["revision"]


def test_simulation_rejects_empty_existing_unknown_scenario_and_invalid_assumptions(client, plan):
    assert freeze(client, plan).status_code == 422
    assert freeze(client, plan, scenario_id=plan['scenarios'][0]['id']).status_code == 422
    assert freeze(client, plan, residential_m2_per_person=0).status_code == 422
    assert freeze(client, plan, scenario_id='00000000-0000-0000-0000-000000000000').status_code == 422


def test_space_use_totals_are_validated():
    payload = {"footprint": building()['geometry'], "residents": 10,
               "space_uses": [{"use": "residential", "floor_area_m2": 100, "residents": 9}]}
    with pytest.raises(ValidationError, match="sum to the building total"):
        Building(**payload)


def test_excluded_gfa_keeps_physical_floor_demand(client, plan, parcel_source, tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path / "excluded.sqlite"))
    plan = command(client, plan, "save_building", building(floors=1, counts_gfa=False, counts_far=False))
    response = freeze(client, plan)
    assert response.status_code == 201, response.text
    study = PlanningStudy(**store.load_document(response.json()["id"], "study")["inputs"])
    project = study.projects[0]
    analysis = geometry.analyze(project.site, project.development)
    assert analysis["floor_areas"] == [0]
    assert project.development.buildings[0].space_uses[0].floor_area_m2 > 0
    loads = demand.calculate(project.development, analysis["floor_areas"], parameters("base"))
    assert loads["energy_kwh_day"] > 0
