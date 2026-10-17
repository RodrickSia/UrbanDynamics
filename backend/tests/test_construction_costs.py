from copy import deepcopy

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import zoning
from app.services import parcels
from app.services.zoning import costs
from app.services.zoning.cost_models import CostSettings
from app.services.zoning.geometry import projected


def rectangle(west=106.76, south=10.82, east=106.762, north=10.822):
    return {'type': 'Polygon', 'coordinates': [[[west, south], [east, south],
        [east, north], [west, north], [west, south]]]}


def building(**extra):
    return {'parcel_id': '3885881', 'geometry': rectangle(106.7602, 10.8202, 106.7605, 10.8205),
            'floors': 2, 'floor_height': 3.2, 'space_use_id': 'residential', **extra}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('WAREHOUSE_PASSWORD', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('ZONING_DATA_DIR', str(tmp_path))
    app = FastAPI()
    app.include_router(zoning.router)
    return TestClient(app)


@pytest.fixture
def plan(client):
    response = client.post('/api/v1/zoning/plans', json={'name': 'Cost study', 'study_area': rectangle()})
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def parcel_source(monkeypatch):
    monkeypatch.setattr(zoning, 'warehouse_configured', lambda: True)
    monkeypatch.setattr(parcels, 'development_parcel', lambda _: {
        'id': '3885881', 'geometry': rectangle(), 'land_use': 'ODT'})


def command(client, plan, action, payload=None, scenario_id=None, status=200):
    response = client.post(f"/api/v1/zoning/plans/{plan['id']}/commands", json={
        'revision': plan['revision'], 'action': action, 'payload': payload or {},
        'scenario_id': scenario_id or plan['scenarios'][1]['id']})
    assert response.status_code == status, response.text
    return response.json()


def test_physical_floors_not_regulatory_gfa_and_included_extras():
    item = {**building(counts_gfa=False, counts_far=False), 'id': 'b', 'name': 'House'}
    settings = CostSettings.model_validate({'profile': {'unit_price': 5300000, 'foundation_factor': .5,
        'roof_factor': .4}, 'vat_pct': 10, 'reserve_pct': 5,
        'extras': {'design': {'amount': 10000000, 'included': True},
                   'permit': {'amount': 2000000, 'included': False}}})
    result = costs.calculate({'study_area': rectangle()}, {'kind': 'proposal', 'buildings': [item]}, settings)
    area = projected(item['geometry']).area
    assert result['buildings'][0]['converted_m2'] == pytest.approx(area * 2.9)
    assert result['construction'] == pytest.approx(round(area * 2.9 * 5300000), abs=1)
    assert result['extras'] == 2000000
    assert result['total'] == pytest.approx(round((result['construction'] + 2000000)*1.1*1.05), abs=1)


def test_demolition_uses_building_floors_and_unions_overlapping_masks(monkeypatch):
    geometry = rectangle(106.7602, 10.8202, 106.7605, 10.8205)
    calls = []
    def inventory(site, study):
        calls.append(site)
        return [{'id': 'old', 'geometry': geometry, 'floors': 3}]
    monkeypatch.setattr(costs.baseline, 'buildings', inventory)
    scenario = {'kind': 'proposal', 'demolition_masks': [
        {'id': 'm1', 'geometry': rectangle()}, {'id': 'm2', 'geometry': rectangle()}]}
    result = costs.calculate({'study_area': rectangle()}, scenario, CostSettings(demolition_rate=200000))
    assert len(calls) == 1
    assert len(result['demolitions']) == 1
    assert result['demolition'] == pytest.approx(round(projected(geometry).area * 3 * 200000), abs=1)


def test_unknown_demolition_never_becomes_a_zero_total(monkeypatch):
    monkeypatch.setattr(costs.baseline, 'buildings', lambda *args: None)
    scenario = {'kind': 'proposal', 'demolition_masks': [{'id': 'm', 'geometry': rectangle()}]}
    result = costs.calculate({'study_area': rectangle()}, scenario, CostSettings())
    assert result['total'] is None
    assert result['demolition'] is None
    fixed = costs.calculate({'study_area': rectangle()}, scenario,
        CostSettings(demolition_area_m2=240, demolition_rate=200000))
    assert fixed['total'] == 48000000
    assert fixed['demolition_basis'] == 'user_area'


def test_reference_has_no_construction_bill():
    result = costs.calculate({'study_area': rectangle()}, {'kind': 'reference'}, CostSettings())
    assert result['total'] == 0
    assert result['buildings'] == []


def test_included_vat_demolition_and_extras_are_not_added_again():
    settings = CostSettings.model_validate({'demolition_included': True, 'vat_included': True,
        'vat_pct': 10, 'reserve_pct': 5, 'extras': {'design': {'amount': 100, 'included': True}}})
    scenario = {'kind': 'proposal', 'buildings': [{**building(), 'id': 'b', 'name': 'House'}],
        'demolition_masks': [{'geometry': rectangle()}]}
    result = costs.calculate({'study_area': rectangle()}, scenario, settings)
    assert result['demolition'] == result['vat'] == result['extras'] == 0
    assert result['total'] == pytest.approx(result['construction'] * 1.05, abs=1)


def test_deleted_building_override_is_not_offered_for_resave():
    settings = CostSettings.model_validate({'building_overrides': {'deleted': {'unit_price': 10}}})
    result = costs.calculate({'study_area': rectangle()}, {'kind': 'proposal'}, settings)
    assert result['settings']['building_overrides'] == {}
    assert 'deleted' in settings.building_overrides


def test_additional_area_requires_confirmation_and_has_its_own_factor():
    item = {'name': 'Basement', 'area_m2': 80, 'factor': 1.5}
    with pytest.raises(ValueError):
        CostSettings.model_validate({'profile': {'additional_areas': [item]}})
    settings = CostSettings.model_validate({'profile': {'additional_areas': [item],
        'additional_areas_confirmed': True, 'floor_area_m2': 240, 'foundation_factor': 0, 'roof_factor': 0}})
    result = costs.calculate({'study_area': rectangle()}, {'kind': 'proposal',
        'buildings': [{**building(), 'id': 'b', 'name': 'House'}]}, settings)
    assert result['buildings'][0]['converted_m2'] == 360


def test_cost_settings_persist_reject_stale_lock_and_remap_clone(client, plan, parcel_source):
    plan = command(client, plan, 'save_building', building())
    original_id = plan['scenarios'][1]['buildings'][0]['id']
    old = deepcopy(plan)
    plan = command(client, plan, 'save_cost_settings', {'profile': {'unit_price': 6000000},
        'building_overrides': {original_id: {'unit_price': 3600000}}})
    command(client, old, 'save_cost_settings', {}, status=409)
    response = client.get(f"/api/v1/zoning/plans/{plan['id']}/costs",
        params={'scenario_id': plan['scenarios'][1]['id'], 'revision': plan['revision']})
    assert response.status_code == 200, response.text
    assert response.json()['buildings'][0]['unit_price'] == 3600000
    plan = command(client, plan, 'add_scenario', {'name': 'Copy'})
    clone = plan['scenarios'][-1]
    assert clone['cost_settings']['building_overrides'][clone['buildings'][0]['id']]['unit_price'] == 3600000
    loaded = client.get(f"/api/v1/zoning/plans/{plan['id']}").json()
    assert loaded['scenarios'][-1]['cost_settings'] == clone['cost_settings']
    plan = command(client, plan, 'lock_scenario', {'locked': True})
    command(client, plan, 'save_cost_settings', {}, status=422)
    command(client, plan, 'save_cost_settings', {}, plan['scenarios'][0]['id'], status=422)


@pytest.mark.parametrize('payload', [{'vat_pct': -1}, {'profile': {'unit_price': -1}},
    {'profile': {'location_factor': 0}}, {'demolition_area_m2': -2}, {'reserve_pct': float('inf')}])
def test_reject_invalid_assumptions(payload):
    with pytest.raises(ValueError):
        CostSettings.model_validate(payload)
