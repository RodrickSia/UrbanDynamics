from shapely.geometry import box, mapping
import pytest

from app.services.area_indicators import engine
from app.services.area_indicators.models import AreaRequest, Assumptions
from app.services.zoning.geometry import projected


def area():
    return mapping(box(106.760, 10.820, 106.762, 10.822))


def test_existing_housing_capacity_uses_available_generated_buildings(monkeypatch):
    geometry = mapping(box(106.7602, 10.8202, 106.7605, 10.8205))
    monkeypatch.setattr(engine.sources, 'population', lambda _: {
        'year': 2025, 'value': 100, 'covered_m2': projected(area()).area, 'files': []})
    monkeypatch.setattr(engine.sources, 'parcels', lambda _: [])
    monkeypatch.setattr(engine.transit, 'proximity', lambda *_: None)
    monkeypatch.setattr(engine.building_baseline, 'buildings', lambda *_: [
        {'id': 'g-1', 'geometry': geometry, 'floors': 4, 'height_m': 12.8, 'source': 'generated v1'}])
    result = engine.analyze(AreaRequest(geometry=area()))
    expected = projected(geometry).area * 4 * .8 / 70
    assert result['baseline']['housing_capacity'] == expected
    assert result['existing_buildings'] == {
        'status': 'estimated', 'count': 1, 'source': 'Generated residential 3D building model',
        'floor_area_m2': projected(geometry).area * 4, 'coverage': 'unknown',
    }
    assert result['baseline']['jobs_capacity'] is None


def test_existing_housing_remains_unknown_if_generated_inventory_unavailable(monkeypatch):
    monkeypatch.setattr(engine.sources, 'population', lambda _: None)
    monkeypatch.setattr(engine.sources, 'parcels', lambda _: None)
    monkeypatch.setattr(engine.transit, 'proximity', lambda *_: None)
    monkeypatch.setattr(engine.building_baseline, 'buildings', lambda *_: None)
    result = engine.analyze(AreaRequest(geometry=area()))
    assert result['baseline']['housing_capacity'] is None
    assert result['existing_buildings']['status'] == 'unavailable'


def test_capacity_clips_to_area_and_deduplicates_source_footprints():
    geometry = mapping(box(106.761, 10.821, 106.763, 10.823))
    record = {'geometry': geometry, 'floors': 2}
    result = engine.existing_building_metrics([record, record,
        {'geometry': mapping(box(106.77, 10.83, 106.78, 10.84)), 'floors': None}],
        projected(area()), Assumptions())
    expected = projected(geometry).intersection(projected(area())).area * 2 * .8 / 70
    assert result['housing_capacity'] == pytest.approx(expected)
    assert result['inventory']['count'] == 1


@pytest.mark.parametrize('floors', [None, 0, -1, float('nan')])
def test_unknown_floor_counts_do_not_look_like_complete_capacity(floors):
    result = engine.existing_building_metrics([{'geometry': area(), 'floors': floors}],
        projected(area()), Assumptions())
    assert result['housing_capacity'] is None
    assert result['inventory']['status'] == 'partial'


def test_outside_inventory_does_not_imply_zero_housing():
    result = engine.existing_building_metrics([
        {'geometry': mapping(box(106.77, 10.83, 106.78, 10.84)), 'floors': 3}],
        projected(area()), Assumptions())
    assert result['housing_capacity'] is None
    assert result['inventory']['status'] == 'unavailable'
