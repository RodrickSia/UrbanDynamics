import json

import pytest
from shapely.geometry import box, mapping

from test_development import building, parcel_source  # noqa: F401
from test_zoning import client, plan, command  # noqa: F401
from app.services.area_indicators import engine, sources, transit
from app.services.area_indicators.models import Assumptions
from app.services.zoning.geometry import projected


def rect(w=106.760, s=10.820, e=106.762, n=10.822):
    return mapping(box(w, s, e, n))


@pytest.fixture(autouse=True)
def data_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(sources, 'population', lambda geometry: {'year': 2025, 'value': 100,
        'covered_m2': projected(geometry).area, 'files': ['test.tif']})
    monkeypatch.setattr(sources, 'parcels', lambda geometry: [{'code': 'ODT', 'geometry': geometry}])
    monkeypatch.setenv('INDICATORS_TRANSIT_PATH', str(tmp_path/'missing.geojson'))


def test_area_baseline_and_missing_are_not_zero(client, monkeypatch):
    response = client.post('/api/v1/indicators/area', json={'geometry': rect()})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['baseline']['population'] == 100
    assert data['baseline']['water_m3_day'] == 12
    assert data['baseline']['energy_kwh_day'] == 300
    assert data['baseline']['waste_kg_day'] == 100
    assert data['baseline']['jobs_needed'] == 50
    assert data['baseline']['jobs_capacity'] is None
    assert data['baseline']['jobs_balance'] is None
    assert data['baseline']['housing_capacity'] is None
    assert data['land_use'][0]['percent'] == pytest.approx(100)
    assert data['transit']['coverage_percent'] is None
    monkeypatch.setattr(sources, 'population', lambda _: None)
    monkeypatch.setattr(sources, 'parcels', lambda _: None)
    missing = client.post('/api/v1/indicators/area', json={'geometry': rect()}).json()
    assert all(value is None for value in missing['baseline'].values())
    assert missing['land_use'] is None


def test_partial_population_does_not_become_a_total(client, monkeypatch):
    monkeypatch.setattr(sources, 'population', lambda g: {'year': 2024, 'value': 10, 'covered_m2': projected(g).area/2})
    result = client.post('/api/v1/indicators/area', json={'geometry': rect()}).json()
    assert result['baseline']['population'] is None
    assert result['population_source']['covered_population'] == 10
    assert result['population_source']['coverage_percent'] == pytest.approx(50)
    monkeypatch.setattr(sources, 'population', lambda g: {'year': 2024, 'value': 0, 'covered_m2': projected(g).area})
    assert client.post('/api/v1/indicators/area', json={'geometry': rect()}).json()['baseline']['population'] == 0


def test_union_partition_includes_holes_conflicts_and_unmapped():
    area = projected(rect())
    source = rect()
    source['coordinates'] = [source['coordinates'][0], rect(106.7604,10.8204,106.7606,10.8206)['coordinates'][0]]
    rows = engine.land_distribution([{'code':'ODT','geometry':source}, {'code':'ODT','geometry':source},
        {'code':'TMD','geometry':rect(106.761,10.821,106.763,10.823)}], area)
    assert sum(r['percent'] for r in rows) == pytest.approx(100)
    assert {'ODT','conflict','unmapped'} <= {r['code'] for r in rows}
    assert all(r['area_m2'] <= area.area for r in rows)


def test_proposals_clip_floor_programs_and_toggle_without_mutating_plan(client, plan, parcel_source):
    plan = command(client, plan, 'save_building', building(floors=2, floor_overrides=[
        {'floor':1,'floor_height':4,'space_use_id':'office','counts_gfa':True,'counts_far':True}]))
    original = client.get(f"/api/v1/zoning/plans/{plan['id']}").json()
    geometry = plan['scenarios'][1]['buildings'][0]['geometry']
    geom = projected(geometry)
    body = {'geometry':geometry, 'plan_id':plan['id'], 'revision':plan['revision'],
            'scenario_id':plan['scenarios'][1]['id'], 'include_scenario':True}
    data = client.post('/api/v1/indicators/area', json=body).json()
    values = data['proposal']
    assert values['population'] == pytest.approx(geom.area*.8/35)
    assert values['housing_capacity'] == pytest.approx(geom.area*.8/70)
    assert values['jobs_capacity'] == pytest.approx(geom.area*.8/20)
    assert values['jobs_balance'] == pytest.approx(values['jobs_capacity']-values['jobs_needed'])
    assert client.post('/api/v1/indicators/area', json={**body,'include_scenario':False}).json()['proposal'] is None
    assert client.post('/api/v1/indicators/area', json={**body,'scenario_id':plan['scenarios'][0]['id']}).json()['proposal'] is None
    assert client.post('/api/v1/indicators/area', json={**body,'revision':1}).status_code == 409
    assert client.get(f"/api/v1/zoning/plans/{plan['id']}").json() == original
    # AOI cuts through a footprint; only intersected floor area contributes.
    half = box(*geom.bounds).intersection(box(geom.bounds[0],geom.bounds[1],geom.centroid.x,geom.bounds[3]))
    proposal = engine.proposal_metrics(plan['scenarios'][1], half, Assumptions())
    assert 0 < proposal['population'] < values['population']


def test_transit_external_stops_union_and_snapshot_coverage(monkeypatch, tmp_path):
    path = tmp_path/'stops.geojson'
    document = {'type':'FeatureCollection', 'source':'Fixture', 'captured_at':'2026-10-14', 'bbox':[106,10,108,12],
        'features':[{'type':'Feature','geometry':{'type':'Point','coordinates':[106.7599,10.821]},'properties':{}}]*2}
    path.write_text(json.dumps(document))
    monkeypatch.setenv('INDICATORS_TRANSIT_PATH', str(path))
    result = transit.proximity(projected(rect()),500)
    assert result['coverage_percent'] == pytest.approx(100)
    assert result['status'] == 'proxy'
    document['bbox'] = [106.760,10.820,106.762,10.822]
    path.write_text(json.dumps(document)); transit.read_snapshot.cache_clear()
    assert transit.proximity(projected(rect()),500)['coverage_percent'] is None


def test_unknown_uses_and_excluded_floors_do_not_invent_jobs_or_hide_demand():
    source = {'geometry': rect(), 'floors': 2, 'floor_height': 3.2, 'space_use_id': 'residential',
              'counts_gfa': False, 'counts_far': False}
    area = projected(rect())
    values = engine.proposal_metrics({'buildings': [source]}, area, Assumptions())
    assert values['housing_capacity'] == 0
    assert values['energy_kwh_day'] > 0
    source.update(space_use_id='other', counts_gfa=True)
    values = engine.proposal_metrics({'buildings': [source]}, area, Assumptions())
    assert values['jobs_capacity'] is None
    assert values['jobs_balance'] is None
    assert values['energy_kwh_day'] is None


@pytest.mark.parametrize('payload', [
    {'geometry':mapping(box(0,0,1,1))}, {'geometry':rect(),'include_scenario':True},
    {'geometry':rect(),'assumptions':{'work_m2_per_job':0}},
    {'geometry':{'type':'Polygon','coordinates':[[[106.76,10.82],[106.77,10.83],[106.76,10.83],[106.77,10.82],[106.76,10.82]]]}}
])
def test_invalid_requests(client, payload):
    assert client.post('/api/v1/indicators/area', json=payload).status_code == 422
