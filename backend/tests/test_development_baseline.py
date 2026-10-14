import json
from pathlib import Path

import pytest
from shapely.affinity import translate
from shapely.geometry import mapping, shape

from test_zoning import client, plan, command, rectangle, add_type, draw  # noqa: F401
from test_development import parcel_source  # noqa: F401
from app.services.zoning import baseline
from app.services.zoning.geometry import projected
from app.services.simulation.engine import polygon_and_area
from app.services.simulation.integrated.geometry import analyze
from app.services.simulation.integrated.models import Design
from app.services.simulation.models import PolygonInput


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
