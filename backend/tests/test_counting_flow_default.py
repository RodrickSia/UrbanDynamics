import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.simulation.planning import counting_reference, system_demo
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.context import build_context

@pytest.fixture
def reference(tmp_path, monkeypatch):
    monkeypatch.setenv('PLANNING_SYSTEM_DEMO_ENABLED','1')
    monkeypatch.setenv('PLANNING_COUNTING_REFERENCE_DIR',str(tmp_path))
    monkeypatch.delenv('PLANNING_DEFAULT_COUNTING_REFERENCE_ID',raising=False)
    doc={'schema_version':'traffic-counts-identity-repair-1','simulation_ready':False,
        'camera_id':'test','source_sha256':'a'*64,'tracks_sha256':'b'*64,
        'observation':{'duration_seconds':500/30},'repaired_crossings':19,
        'counts':[{'vehicle_class':'motorcycle','count':17},{'vehicle_class':'car','count':1},{'vehicle_class':'bus','count':1}]}
    raw=json.dumps(doc).encode();identifier=hashlib.sha256(raw).hexdigest()
    (tmp_path/(identifier+'.json')).write_bytes(raw)
    (tmp_path/'default-reference.txt').write_text(identifier+'\n')
    return identifier

def test_rate_conservation_supported_types_and_per_road_override(reference):
    result=counting_reference.flow_default(reference,road_id='OSM-123')
    assert result['vehicles_hour']==pytest.approx(4104)
    assert sum(result['sample_vehicles_hour_by_class'].values())==pytest.approx(result['vehicles_hour'])
    assert result['sumo_supported_vehicles_hour']==pytest.approx(3888)
    assert result['source_kind']=='synthetic' and result['calibrated'] is False
    assert counting_reference.flow_default(reference,'OSM-456')['vehicles_hour']==result['vehicles_hour']
    for measured in (0,500):
        override=counting_reference.flow_default(reference,'OSM-123',measured)
        assert override['vehicles_hour']==measured and override['source_kind']=='observed'
    for invalid in (-1,float('nan'),float('inf'),True):
        with pytest.raises(ValueError):counting_reference.flow_default(reference,observed_vehicles_hour=invalid)

def test_constant_demo_proxy_and_explicit_zero_override(reference):
    default=counting_reference.prior(reference)
    assert default.cars==[216]*24 and default.motorcycles==[3672]*24
    assert default.source_kind=='synthetic'
    explicit=counting_reference.prior(reference,0)
    assert explicit.cars==[0]*24 and explicit.motorcycles==[0]*24
    assert max(a+b for a,b in zip(counting_reference.prior(reference,800).cars,counting_reference.prior(reference,800).motorcycles))==800

def test_default_api_is_demo_gated_and_reports_transfer(reference,monkeypatch):
    with TestClient(app) as client:
        r=client.get('/api/v1/planning/demo/system/traffic-default')
        assert r.status_code==200 and r.json()['vehicles_hour']==pytest.approx(4104)
        assert r.json()['basis']=='both_directions_combined'
        monkeypatch.delenv('PLANNING_SYSTEM_DEMO_ENABLED')
        assert client.get('/api/v1/planning/demo/system/traffic-default').status_code==404

def test_prepare_uses_installed_default_and_preserves_explicit_override(reference,tmp_path,monkeypatch):
    from app.services.simulation.planning.presets import rectangle
    from app.services.simulation.integrated.background import publish
    monkeypatch.setenv('PLANNING_SYSTEM_SNAPSHOT_DIR',str(tmp_path/'snapshots'))
    site=rectangle(106.758,10.82)
    doc={'schema_version':1,'captured_at':'2026-10-13T00:00:00Z','bbox':[106.75,10.81,106.77,10.83],
         'parcels':{'features':[{'type':'Feature','id':1,'properties':{},'geometry':site}]},'layers':{},'osm':{'elements':[]}}
    snapshot=publish(doc,tmp_path/'snapshots')
    def prepare(**values):
        return PlanningStudy(**system_demo.prepare(system_demo.Prepare(snapshot_id=snapshot,parcel_ids=['1'],**values)))
    study=prepare()
    assert study.traffic_prior.counting_reference_id==reference
    assert build_context(study)['resolved_background']['traffic']['motorcycles']==[3672]*24
    zero=prepare(traffic_peak_vehicles_hour=0)
    assert build_context(zero)['resolved_background']['traffic']['motorcycles']==[0]*24
    assert study.traffic_prior.source_kind=='synthetic'
