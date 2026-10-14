import json
from pathlib import Path

import pytest
from shapely.affinity import translate
from shapely.geometry import mapping, shape

from test_zoning import client, plan, command, rectangle, add_type, draw  # noqa: F401
from test_development import parcel_source  # noqa: F401
from app.services.zoning import baseline, development
from app.services.zoning.geometry import projected
from app.services.simulation.engine import polygon_and_area
from app.services.simulation.integrated.geometry import analyze
from app.services.simulation.integrated.models import Design
from app.services.simulation.models import PolygonInput


def test_zoning_baseline_queries_all_intersecting_generated_buildings(monkeypatch):
    statements = []
    a = rectangle(106.7601, 10.8201, 106.7603, 10.8203)
    b = rectangle(106.7607, 10.8207, 106.7612, 10.8212)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, parameters=None):
            statements.append((sql, parameters))
            return self
        def fetchone(self): return ['buildings.synthetic_residential']
        def fetchall(self): return [(json.dumps(g), 12.8, 4, 'fixture', 'v1') for g in [a, b]]
    monkeypatch.setattr(baseline, 'warehouse_configured', lambda: True)
    monkeypatch.setattr(baseline, 'connect_to_warehouse', Connection)
    site = {'id': 'zone:00000000-0000-0000-0000-000000000001', 'geometry': rectangle()}
    records = baseline.buildings(site, rectangle())
    assert len(records) == 2
    assert len({b['id'] for b in records}) == 2
    assert 'ST_Intersects' in statements[-1][0]
    assert json.loads(statements[-1][1][0]) == site['geometry']
    assert all(projected(site['geometry']).buffer(.001).covers(projected(b['geometry'])) for b in records)


def test_setbacks_measure_real_parcel_boundary_not_study_clip():
    parcel = {'geometry': rectangle(), 'area_m2': projected(rectangle()).area}
    footprint = rectangle(106.7602, 10.8202, 106.7605, 10.8205)
    records = [{'geometry': footprint, 'height_m': 12.8, 'floors': 4}]
    # Study edge cuts the footprint; it must not become a new cadastral boundary.
    report = baseline.report(parcel, rectangle(106.7603, 10.82, 106.762, 10.822), records)
    assert report['metrics']['setbacks'] == pytest.approx(
        projected(footprint).distance(projected(parcel['geometry']).boundary))
    assert report['metrics']['gfa_m2'] < projected(footprint).area * 4


def test_proposed_setback_is_geometry_distance_without_claiming_frontage(plan):
    from test_development import building
    parcel = {'geometry': rectangle(), 'area_m2': projected(rectangle()).area}
    block = {**building(), 'height_m': 6.4, 'counts_gfa': True, 'counts_far': True}
    report = development.validation(plan, plan['scenarios'][1], parcel, [block])
    setback = next(row for row in report['checks'] if row['rule'] == 'setbacks')
    assert setback['actual'] == pytest.approx(projected(block['geometry']).distance(projected(parcel['geometry']).boundary))
    assert setback['unit'] == 'm'
    assert setback['assumption_status'] == 'UNKNOWN'
    assert development.minimum_setback(parcel, []) is None


def test_streamed_buildings_fill_baseline_gap_without_double_counting(client, plan, parcel_source, monkeypatch):
    monkeypatch.setattr(baseline, 'buildings', lambda *_: None)
    geometry = rectangle(106.7602, 10.8202, 106.7605, 10.8205)
    feature = {'type': 'Feature', 'id': 'goong-1', 'geometry': geometry, 'properties': {'height': 16}}
    path = f"/api/v1/zoning/plans/{plan['id']}/development/parcels/3885881/baseline?scenario_id={plan['scenarios'][0]['id']}"
    response = client.post(path, json={'features': [feature, feature]})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['baseline']['metrics']['max_height'] == 16
    assert report['baseline']['metrics']['gfa_m2'] == pytest.approx(projected(geometry).area * 5)
    assert report['baseline']['metrics']['setbacks'] > 0
    assert 'Goong' in report['baseline']['source']
    # Canonical generated footprints take precedence over overlapping map context.
    monkeypatch.setattr(baseline, 'buildings', lambda *_: [
        {'id': 'generated', 'geometry': geometry, 'height_m': 12.8, 'floors': 4, 'source': 'generated'}])
    report = client.post(path, json={'features': [feature]}).json()
    assert report['baseline']['metrics']['gfa_m2'] == pytest.approx(projected(geometry).area * 4)


def test_scenario_setback_respects_demolition_without_changing_existing(client, plan, parcel_source, monkeypatch):
    geometry = rectangle(106.7602, 10.8202, 106.7605, 10.8205)
    monkeypatch.setattr(baseline, 'buildings', lambda *_: [
        {'geometry': geometry, 'height_m': 12.8, 'floors': 4}])
    path = f"/api/v1/zoning/plans/{plan['id']}/development/parcels/3885881"
    proposal = plan['scenarios'][1]['id']
    # Load the canonical parcel before a demolition command.
    current = client.get(path, params={'scenario_id': proposal}).json()
    assert current['scenario_setback_m'] == current['baseline']['metrics']['setbacks']
    plan = command(client, plan, 'demolish_parcel', {'parcel_id': '3885881', 'confirm': True})
    demolished = client.get(path, params={'scenario_id': proposal}).json()
    assert demolished['scenario_setback_m'] is None
    assert demolished['baseline']['metrics']['setbacks'] > 0


def test_existing_metrics_and_scenario_zoning_are_separate(client, plan, parcel_source, monkeypatch):
    records = [{'id':'source-1', 'geometry':rectangle(106.7602,10.8202,106.7605,10.8205),
                'height_m':12.8, 'floors':4, 'source':'estimated', 'space_use_id':'residential'}]
    monkeypatch.setattr(baseline, 'buildings', lambda *_: records)
    def read(scenario):
        return client.get(f"/api/v1/zoning/plans/{plan['id']}/development/parcels/3885881?scenario_id={scenario['id']}").json()
    current = read(plan['scenarios'][0])
    assert current['baseline']['metrics']['gfa_m2'] == pytest.approx(projected(records[0]['geometry']).area*4)
    assert current['baseline']['metrics']['max_height'] == 12.8
    assert current['zoning'] == []
    plan = add_type(client, plan, 'TMD')
    plan = command(client, plan, 'draw', {'geometry': rectangle(), 'type_id': plan['types'][-1]['id'], 'policy':'replace'})
    proposed = read(plan['scenarios'][1])
    assert proposed['parcel']['land_use'] == 'ODT'
    assert proposed['zoning'][0]['code'] == 'TMD'
    assert proposed['zoning'][0]['percent'] == pytest.approx(100)
    assert read(plan['scenarios'][0])['zoning'] == []
    monkeypatch.setattr(baseline, 'buildings', lambda *_: None)
    assert read(plan['scenarios'][0])['baseline']['metrics'] is None


def test_saved_boundary_roundoff_runs_but_real_outside_geometry_is_rejected():
    fixture=json.loads((Path(__file__).parent/'fixtures/development-boundary-roundoff.json').read_text())
    site=PolygonInput(**fixture['site']); footprint=PolygonInput(**fixture['footprint'])
    area=polygon_and_area(site)[1]; roof=polygon_and_area(footprint)[1]
    design=Design(buildings=[{'footprint':footprint, 'floors':2, 'height_m':6.4}], paved_m2=area-roof)
    assert analyze(site,design)['metrics']['floor_area_m2'] == pytest.approx(roof*2)
    outside=mapping(translate(shape(fixture['footprint']),xoff=.0000001))
    design.buildings[0].footprint=PolygonInput(**outside)
    with pytest.raises(ValueError,match='inside the site'):
        analyze(site,design)
