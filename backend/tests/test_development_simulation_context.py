from copy import deepcopy
from io import BytesIO
from unittest.mock import patch

import pytest
from shapely.geometry import shape

from test_development import building
from test_zoning import rectangle
from app.services.zoning import simulation_context as context
from app.services.zoning.simulation import SimulationInput, SimulationRunInput, study_from_plan
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.osm_network import network_document, source_specification

SID='00000000-0000-0000-0000-000000000002'


def plan():
    return {'id':'controlled','name':'Controlled test','revision':1,'study_area':rectangle(),
            'parcels':{'3885881':{'geometry':rectangle()}},
            'scenarios':[{'id':SID,'kind':'proposal','name':'Proposal',
                          'buildings':[{**building(),'name':'Same building','counts_gfa':True,'counts_far':True}]}]}


@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setenv('DEVELOPMENT_CONTEXT_DIR',str(tmp_path/'roads'))
    monkeypatch.setenv('PLANNING_SYSTEM_SNAPSHOT_DIR',str(tmp_path/'snapshots'))
    monkeypatch.setenv('PLANNING_COUNTING_REFERENCE_DIR',str(tmp_path/'counting'))
    from app.services.simulation.planning import counting_reference
    monkeypatch.setattr(counting_reference,'default_identifier',lambda:None)


def existing():
    return [{**building(),'name':'Existing','height_m':6.4}]


def test_unavailable_optional_counting_reference_keeps_plan_simulation_available(monkeypatch):
    from app.services.simulation.planning import counting_reference
    monkeypatch.setattr(counting_reference, 'default_identifier', lambda: 'f' * 64)
    def unavailable(_):
        raise ValueError('Demo disabled')
    monkeypatch.setattr(counting_reference, 'prior', unavailable)
    prior = context.traffic_prior()
    assert prior.cars[18] + prior.motorcycles[18] == 400
    assert prior.source_kind == 'synthetic'
    assert prior.counting_reference_id is None
    with patch('app.services.zoning.baseline.buildings', return_value=existing()):
        study = study_from_plan(plan(), SimulationInput(revision=1, scenario_id=SID, parcel_id='3885881'))
    assert study.traffic_prior.counting_reference_id is None
    assert run_screening(study)['options']


def test_unchanged_building_preserves_surfaces_and_all_demand():
    with patch('app.services.zoning.baseline.buildings',return_value=existing()):
        study=study_from_plan(plan(),SimulationInput(revision=1,scenario_id=SID,parcel_id='3885881'))
    result=run_screening(study)
    rows={r['metric']:r for r in result['options'][0]['comparison']}
    for key in ('residents','freshwater_m3_day','energy_kwh_day','green_m2','impervious_m2','unretained_runoff_m3'):
        assert rows[key]['delta'] == pytest.approx(0),key
    assert study.projects[0].baseline.green_m2 > 0
    assert study.development_context['surfaces']['status']=='assumed'
    assert study.traffic_prior.cars[18]+study.traffic_prior.motorcycles[18]==400


def test_landscape_redesign_requires_explicit_choice():
    with patch('app.services.zoning.baseline.buildings',return_value=existing()):
        study=study_from_plan(plan(),SimulationInput(revision=1,scenario_id=SID,parcel_id='3885881',landscape_mode='redesign',green_open_percent=80))
    assert study.projects[0].development.green_m2 > study.projects[0].baseline.green_m2
    assert 'ALL open ground' in study.development_context['surfaces']['note']


def test_historical_green_is_clipped_and_roofs_are_removed():
    site=rectangle()
    document={'osm':{},'landcover':{'features':[{'geometry':site,'properties':{'class_code':10}}],
                                   'metadata':{'year':2021,'dataset':'ESA WorldCover'}}}
    buildings=[{'footprint':building()['geometry']}]
    design, source=context.surfaces(site,buildings,document)
    assert design['green_m2'] > 0
    assert design['paved_m2'] == pytest.approx(0,abs=.1)
    assert source['unclassified_surface_m2'] == pytest.approx(0,abs=.1)
    assert source['landcover']['year']==2021


def osm_response():
    import json
    return json.dumps({'elements':[{'type':'way','id':1,'tags':{'highway':'residential'},
                        'geometry':[{'lon':106.759,'lat':10.82},{'lon':106.763,'lat':10.82}]}]}).encode()


def test_arbitrary_area_download_is_cached_and_frozen(monkeypatch):
    calls=[]
    def fetch(request,timeout):
        calls.append(request.data)
        return BytesIO(osm_response())
    monkeypatch.setattr(context,'urlopen',fetch)
    region=shape(rectangle())
    identifier,document=context.acquire_network(region,750)
    second, _=context.acquire_network(region,750)
    assert identifier==second and len(calls)==1
    assert shape(rectangle()).within(shape({'type':'Polygon','coordinates':[[
        [document['bbox'][0],document['bbox'][1]],[document['bbox'][2],document['bbox'][1]],
        [document['bbox'][2],document['bbox'][3]],[document['bbox'][0],document['bbox'][3]],
        [document['bbox'][0],document['bbox'][1]]]]}))
    assert b'way' in calls[0]
    path=context.directory()/(identifier+'.json')
    path.write_text('{}')
    with pytest.raises(ValueError,match='integrity'):
        context.load_network(identifier)


def test_download_failure_does_not_fall_back_to_synthetic_roads(monkeypatch):
    def unavailable(*args,**kwargs):
        raise OSError('offline')
    monkeypatch.setattr(context,'urlopen',unavailable)
    with pytest.raises(ValueError,match='No synthetic road fallback'):
        context.acquire_network(shape(rectangle()),750)


def test_native_study_uses_local_osm_beyond_parcel_and_explicit_background(monkeypatch):
    monkeypatch.setattr(context,'urlopen',lambda *a,**kw:BytesIO(osm_response()))
    with patch('app.services.zoning.baseline.buildings',return_value=existing()):
        study=study_from_plan(plan(),SimulationRunInput(revision=1,scenario_id=SID,
            parcel_id='3885881',mode='native',idempotency_key='context-test'))
    assert study.traffic_network_mode=='osm_snapshot'
    assert study.traffic_snapshot_id
    assert study.background_vehicles_hour==400
    assert network_document(study)['bbox'][0] < 106.76
    specification=source_specification(study)
    assert specification['source_snapshot_id']==study.traffic_snapshot_id
    assert specification['map']['features']
    assert study.development_context['traffic']['network']=='osm_local'


def test_oversized_area_rejected_before_download(monkeypatch):
    monkeypatch.setattr(context,'urlopen',lambda *a,**kw:pytest.fail('Should reject before HTTP'))
    with pytest.raises(ValueError,match='25 km'):
        context.acquire_network(shape(rectangle(106,10,107,11)),750)


def test_isolated_plan_storage_does_not_write_warehouse(monkeypatch,tmp_path):
    from app.services.zoning import store
    monkeypatch.setattr(store,'warehouse_configured',lambda:True)
    monkeypatch.setattr(store,'connect_to_warehouse',lambda:pytest.fail('Preview must not write production'))
    monkeypatch.setenv('ZONING_STORAGE','sqlite')
    monkeypatch.setenv('ZONING_DATA_DIR',str(tmp_path))
    doc={'id':'preview','revision':1}
    store.save_new(doc)
    assert store.load('preview')==doc


def test_single_part_cadastral_multipolygon_can_be_simulated():
    from app.services.zoning.simulation import polygon
    value={'type':'MultiPolygon','coordinates':[rectangle()['coordinates']]}
    assert polygon(value,'Parcel').type=='Polygon'


def test_warehouse_roads_preserve_shared_junctions_and_filter_permissions(monkeypatch):
    import json
    from datetime import datetime,timezone
    from src.shared import database
    coords=[(106.76,10.82),(106.761,10.82),(106.761,10.821),(106.76,10.821)]
    rows=[]
    for index in range(4):
        a,b=coords[index],coords[(index+1)%4]
        rows.append((str(index),str(index),str((index+1)%4),'highway.residential',
                     [{'allow':None,'disallow':None,'speed_mps':10}],
                     json.dumps({'type':'LineString','coordinates':[a,b]}),*a,None,*b,None,datetime.now(timezone.utc)))
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):return self
        def fetchone(self):return ['transport.sumo_edge']
        def fetchall(self):return rows
    monkeypatch.setattr(database,'warehouse_configured',lambda:True)
    monkeypatch.setattr(database,'connect_to_warehouse',Connection)
    document=context.warehouse_network([106.75,10.81,106.77,10.83])
    assert document['network_kind']=='warehouse_osm_reconstruction'
    ways=[e for e in document['osm']['elements'] if e['type']=='way']
    assert len(ways)==4
    assert ways[0]['nodes'][-1]==ways[1]['nodes'][0]
    assert ways[0]['tags']['oneway']=='yes'
    assert ways[0]['tags']['maxspeed']=='36.0'
    rows[0]=(*rows[0][:4],[{'allow':'pedestrian','speed_mps':5}],*rows[0][5:])
    assert context.warehouse_network([106.75,10.81,106.77,10.83]) is None
