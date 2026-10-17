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
from app.services.zoning import baseline
from app.services.zoning.simulation import SimulationInput, study_from_plan
from test_zoning import rectangle


def test_zone_site_runs_simulation_without_a_cadastral_parcel(client, plan, monkeypatch, tmp_path):
    from test_zoning import add_type, draw
    monkeypatch.setenv('PLANNING_SQLITE_PATH', str(tmp_path / 'zone.sqlite'))
    monkeypatch.setenv('SIMULATION_WORK_DIR', str(tmp_path / 'solvers'))
    monkeypatch.setattr(baseline, 'buildings', lambda *args: None)
    plan = draw(client, add_type(client, plan), rectangle())
    site_id = f"zone:{plan['scenarios'][1]['zones'][0]['id']}"
    plan = command(client, plan, 'save_building', building(parcel_id=site_id))
    response = client.post(f"/api/v1/zoning/plans/{plan['id']}/simulation/runs", json={
        'revision': plan['revision'], 'scenario_id': plan['scenarios'][1]['id'],
        'parcel_id': site_id, 'mode': 'screening', 'idempotency_key': 'zone-simulation'})
    assert response.status_code == 202, response.text
    result = process_one()
    assert result['status'] == 'succeeded', result


def freeze(client, plan, **settings):
    return client.post(f"/api/v1/zoning/plans/{plan['id']}/simulation/studies", json={
        "revision": plan["revision"], "scenario_id": plan["scenarios"][1]["id"], **settings})


def test_saved_run_can_be_opened_without_resubmitting_and_is_bound_to_revision_scope(client,plan,parcel_source,monkeypatch,tmp_path):
    monkeypatch.setenv('PLANNING_SQLITE_PATH',str(tmp_path/'history.sqlite'))
    monkeypatch.setenv('SIMULATION_WORK_DIR',str(tmp_path/'solvers'))
    monkeypatch.setattr(baseline,'buildings',lambda *args:None)
    plan=command(client,plan,'save_building',building())
    body={'revision':plan['revision'],'scenario_id':plan['scenarios'][1]['id'],'parcel_id':'3885881'}
    submitted=client.post(f"/api/v1/zoning/plans/{plan['id']}/simulation/runs",json={**body,'mode':'screening','idempotency_key':'saved-result-test'}).json()
    assert process_one()['status']=='succeeded'
    path=f"/api/v1/zoning/plans/{plan['id']}/simulation/latest"
    saved=client.post(path,json=body)
    assert saved.status_code==200
    assert saved.json()['job']['id']==submitted['job']['id']
    assert client.post(path,json={**body,'parcel_id':None}).json()['job'] is None
    assert client.post(path,json={**body,'revision':plan['revision']+1}).status_code==409
    assert process_one() is None


def test_development_starts_a_durable_job_in_one_request(client, plan, parcel_source, monkeypatch, tmp_path):
    monkeypatch.setenv('PLANNING_SQLITE_PATH', str(tmp_path / 'atomic.sqlite'))
    monkeypatch.setenv('SIMULATION_WORK_DIR', str(tmp_path / 'solvers'))
    plan = command(client, plan, 'save_building', building())
    payload = {'revision': plan['revision'], 'scenario_id': plan['scenarios'][1]['id'],
               'parcel_id': '3885881', 'mode': 'screening', 'idempotency_key': 'atomic-retry'}
    path = f"/api/v1/zoning/plans/{plan['id']}/simulation/runs"
    response = client.post(path, json=payload)
    assert response.status_code == 202, response.text
    started = response.json()
    assert started['study']['id'] == started['job']['study_id']
    assert client.post(path, json=payload).json()['job']['id'] == started['job']['id']
    changed = client.post(path, json={**payload, 'rainfall_mm': 80})
    assert changed.status_code == 409
    finished = process_one()
    assert finished['id'] == started['job']['id']
    assert finished['status'] == 'succeeded', finished
    assert client.get(f"/api/v1/planning/runs/{finished['result_id']}").status_code == 200


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


def test_scope_filters_buildings_and_counts_overlapping_source_parcels_once(client, plan, parcel_source):
    plan = command(client, plan, 'save_building', building())
    scenario = plan['scenarios'][1]
    second = {**deepcopy(scenario['buildings'][0]), 'id':'second', 'parcel_id':'3885882',
              'geometry':rectangle(106.761,10.821,106.7613,10.8213)}
    scenario['buildings'].append(second)
    plan['parcels']['3885882'] = {**plan['parcels']['3885881'],'id':'3885882'}
    settings = SimulationInput(revision=plan['revision'],scenario_id=scenario['id'])
    whole = study_from_plan(plan,settings)
    assert len(whole.projects) == 1
    assert len(whole.projects[0].development.buildings) == 2
    assert whole.projects[0].site.model_dump(mode='json') == plan['study_area']
    selected = study_from_plan(plan,settings.model_copy(update={'parcel_id':'3885881'}))
    assert len(selected.projects[0].development.buildings) == 1
    assert selected.planning_catalog == 'qcvn_urban_2021'


def test_selected_generated_baseline_can_run_without_new_proposal(client, plan, parcel_source, monkeypatch, tmp_path):
    monkeypatch.setenv('PLANNING_SQLITE_PATH',str(tmp_path/'baseline.sqlite'))
    monkeypatch.setattr(baseline,'buildings',lambda *_: [{'id':'generated', 'geometry':building()['geometry'],
        'floors':2,'height_m':6.4,'space_use_id':'residential','source':'Generated'}])
    response=freeze(client,plan,parcel_id='3885881')
    assert response.status_code == 201,response.text
    study=store.load_document(response.json()['id'],'study')['inputs']
    assert study['projects'][0]['baseline']['buildings']
    assert study['projects'][0]['development']['buildings']
    assert study['projects'][0]['baseline_occupancy'] == 'estimated'
    # Reading a source parcel for simulation must not create an editor revision.
    assert client.get(f"/api/v1/zoning/plans/{plan['id']}").json()['revision'] == plan['revision']


def test_selected_goong_snapshot_is_frozen_in_study(client, plan, parcel_source, monkeypatch, tmp_path):
    monkeypatch.setenv('PLANNING_SQLITE_PATH', str(tmp_path / 'goong.sqlite'))
    monkeypatch.setattr(baseline, 'buildings', lambda *_: None)
    response = freeze(client, plan, parcel_id='3885881', map_buildings={'features': [{
        'id': 11, 'geometry': building()['geometry'], 'properties': {'height': 16, 'levels': 5}}]})
    assert response.status_code == 201, response.text
    study = store.load_document(response.json()['id'], 'study')['inputs']
    block = study['projects'][0]['baseline']['buildings'][0]
    assert block['floors'] == 5
    assert block['height_m'] == pytest.approx(16)
    assert 'Goong' in study['projects'][0]['baseline_source']
    assert freeze(client, plan, map_buildings={'features': []}).status_code == 422


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


def test_whole_scenario_existing_inventory_produces_numeric_demand_comparison(client, plan, parcel_source, monkeypatch):
    from app.services.simulation.planning.engine import run_screening
    monkeypatch.setattr(baseline, 'buildings', lambda *_: [{'id':'existing', 'geometry':building()['geometry'],
        'floors':2, 'height_m':6.4, 'space_use_id':'residential', 'source':'Mapped existing building'}])
    plan = command(client, plan, 'save_building', building(floors=3, demolish=True))
    study = study_from_plan(plan, SimulationInput(revision=plan['revision'], scenario_id=plan['scenarios'][1]['id']))
    assert study.projects[0].baseline_occupancy == 'estimated'
    result = run_screening(study)
    rows = {r['metric']:r for r in result['options'][0]['comparison']}
    for metric in ('residents', 'freshwater_m3_day', 'wastewater_m3_day', 'energy_kwh_day', 'power_peak_kw', 'person_trips_day'):
        assert rows[metric]['before'] > 0
        assert rows[metric]['after'] > rows[metric]['before']
        assert rows[metric]['delta'] is not None
    assert study.utility_zones[0].source_kind == 'synthetic'
    assert study.utility_zones[0].water_capacity_m3_day == pytest.approx(rows['freshwater_m3_day']['before']*1.25)


def test_retained_existing_buildings_are_added_to_new_buildings_without_demolition(client, plan, parcel_source, monkeypatch):
    monkeypatch.setattr(baseline, 'buildings', lambda *_: [{'id':'existing',
        'geometry':rectangle(106.761,10.821,106.7612,10.8212),
        'floors':2, 'height_m':6.4, 'space_use_id':'residential', 'source':'Mapped existing building'}])
    plan = command(client, plan, 'save_building', building())
    study = study_from_plan(plan, SimulationInput(revision=plan['revision'], scenario_id=plan['scenarios'][1]['id']))
    assert len(study.projects[0].baseline.buildings) == 1
    assert len(study.projects[0].development.buildings) == 2


def test_demolition_only_scope_clears_existing_demand(client, plan, parcel_source, monkeypatch):
    from app.services.simulation.planning.engine import run_screening
    monkeypatch.setattr(baseline, 'buildings', lambda *_: [{'id':'existing', 'geometry':building()['geometry'],
        'floors':2, 'height_m':6.4, 'space_use_id':'residential', 'source':'Mapped existing building'}])
    plan = command(client, plan, 'demolish_parcel', {'parcel_id':'3885881', 'confirm':True})
    study = study_from_plan(plan, SimulationInput(revision=plan['revision'], scenario_id=plan['scenarios'][1]['id']))
    result = run_screening(study)
    wastewater = next(r for r in result['options'][0]['comparison'] if r['metric']=='wastewater_m3_day')
    assert wastewater['before'] > 0 and wastewater['after'] == 0
    assert wastewater['delta'] == -wastewater['before']
    # Irrigation on the remaining ground can still require freshwater.


def test_school_floor_program_has_students_staff_and_school_demand(client, plan, parcel_source, monkeypatch):
    from app.services.simulation.planning.engine import run_screening
    monkeypatch.setattr(baseline, 'buildings', lambda *_: None)
    plan = command(client, plan, 'save_building', building(space_use_id='school'))
    study = study_from_plan(plan, SimulationInput(revision=plan['revision'], scenario_id=plan['scenarios'][1]['id']))
    school = study.projects[0].development.buildings[0]
    assert school.use == 'school' and school.residents == 0
    assert school.staff > 0 and school.daily_visitors == school.service_capacity > 0
    result = run_screening(study)
    assert result['options'][0]['state']['metrics']['freshwater_m3_day'] > 0
