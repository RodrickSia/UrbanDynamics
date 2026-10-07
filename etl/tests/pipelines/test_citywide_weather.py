from datetime import datetime,timezone,timedelta
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from shapely.geometry import box,mapping,shape,Point
from src.shared.data_io import write_json,read_json
from src.pipelines.rainwater.config import Settings
from src.pipelines.rainwater import grid,extract,transform,load
from src.pipelines.flood_risk.rules import threshold,evaluate
from src.khoi_service import Service,leader_lock

def cell():
    return {'id':'weather-one','longitude':106.7,'latitude':10.8,'geometry':mapping(box(106.69,10.79,106.71,10.81))}

def response(start,count=72,rain=2):
    return {'longitude':106.75,'latitude':10.75,'hourly_units':{'precipitation':'mm'},
        'hourly':{'time':[int((start+timedelta(hours=i)).timestamp()) for i in range(count)],
                  'precipitation':[rain]*count}}

def forecast():
    start = datetime(2026,10,1,tzinfo=timezone.utc)
    return {'issued_at':start.isoformat(),'fetched_at':start.isoformat(),'expires_at':(start+timedelta(hours=2)).isoformat(),
        'run_id':'a'*32,'source_url':'fixture','grid':{'grid_id':'fixture'},
        'stations':transform.normalize_response(response(start),[cell()])}

def history():
    return {'stations':[{'id':cell()['id'],'threshold_method':'wet_p90_3h',
        'covered_until':'2026-01-01T00:00:00+00:00','thresholds_by_month':{'10':{'wet_windows':100,'p90_3h_mm':4}}}],
        'ready_stations':1,'total_stations':1,'grid_id':'fixture'}

def test_interval_end_is_normalized_to_start_and_selected_cell_recorded():
    station = forecast()['stations'][0]
    assert station['hourly'][0]['time']=='2026-09-30T23:00:00+00:00'
    assert station['longitude']==106.7 and station['selected_longitude']==106.75

@pytest.mark.parametrize('change',[lambda d:d['hourly_units'].update(precipitation='cm'),
    lambda d:d['hourly']['precipitation'].pop(),lambda d:d['hourly']['precipitation'].__setitem__(0,-1),
    lambda d:d['hourly']['precipitation'].__setitem__(0,float('nan'))])
def test_malformed_weather_never_becomes_valid_snapshot(change):
    doc = response(datetime(2026,10,1,tzinfo=timezone.utc)); change(doc)
    with pytest.raises(ValueError): transform.normalize_response(doc,[cell()])

def test_missing_rain_is_gap_not_zero():
    doc = response(datetime(2026,10,1,tzinfo=timezone.utc),count=6)
    doc['hourly']['precipitation'][2]=None
    station = transform.normalize_response(doc,[cell()])[0]
    from src.pipelines.flood_risk.rules import three_hour_windows
    assert len(station['hourly'])==5 and len(three_hour_windows(station))==1

def test_failed_download_cleans_temporary_file_and_preserves_cache(tmp_path,monkeypatch):
    from src.shared import data_io
    import requests
    path = tmp_path/'source.bin'; path.write_bytes(b'previous valid source')
    def fail(*args,**kwargs): raise requests.ConnectionError('DNS unavailable')
    monkeypatch.setattr(data_io,'session',lambda:SimpleNamespace(get=fail))
    with pytest.raises(requests.ConnectionError): data_io.download('https://example.invalid',path)
    assert path.read_bytes()==b'previous valid source'
    assert list(tmp_path.iterdir())==[path]

def test_grid_covers_disconnected_islands_and_is_stable_when_metadata_changes(tmp_path):
    from shapely.geometry import MultiPolygon
    geometry = MultiPolygon([box(106.6,10.7,106.8,10.9),box(106.59,8.67,106.63,8.71)])
    path = tmp_path/'boundary.json'
    document = {'type':'FeatureCollection','features':[{'geometry':mapping(geometry)}],'metadata':{'time':'a'}}
    write_json(path,document)
    cells,meta = grid.build(Settings(path))
    assert any(c['latitude']<9 for c in cells)
    union = __import__('shapely').ops.unary_union([shape(c['geometry']) for c in cells])
    assert union.symmetric_difference(geometry).area<1e-8
    document['metadata']['time']='b'; write_json(path,document)
    assert grid.build(Settings(path))[1]['grid_id']==meta['grid_id']

def test_cached_p90_rejects_future_data():
    h = history()['stations'][0]
    assert threshold(h,10,'2026-10-01T00:00:00Z')==(4,100)
    with pytest.raises(ValueError): threshold(h,10,'2025-10-01T00:00:00Z')

def test_annual_history_is_cached_and_resumes_without_redownload(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    settings = Settings(tmp_path/'unused',history_start_year=2025,history_end_year=2025)
    calls = []
    def fetch(*args,**kwargs):
        calls.append(kwargs)
        return transform.normalize_response(response(datetime(2025,10,1,tzinfo=timezone.utc),100),[cell()])
    monkeypatch.setattr(extract,'request',fetch)
    result = extract.history(settings,[cell()],{'grid_id':'test'})
    assert result['ready_stations']==1
    assert result['stations'][0]['thresholds_by_month']['10']['p90_3h_mm']==6
    assert extract.history(settings,[cell()],{'grid_id':'test'})['ready_stations']==1
    assert len(calls)==1

def test_failed_forecast_publication_preserves_pointer(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path)); monkeypatch.delenv('DATABASE_URL',raising=False)
    load.run(forecast(),history())
    pointer = (tmp_path/'inputs/rainwater_current.json').read_bytes()
    broken = forecast(); broken['run_id']='b'*32; broken['stations'][0]['hourly']=[]
    with pytest.raises(ValueError): load.run(broken,history())
    assert (tmp_path/'inputs/rainwater_current.json').read_bytes()==pointer
    assert load.input_pair()[0]['run_id']=='a'*32

def test_rolling_history_reuses_existing_annual_downloads(tmp_path,monkeypatch):
    from dataclasses import replace
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    settings = Settings(tmp_path/'unused',history_start_year=2024,history_end_year=2024)
    calls = []
    def fetch(*args,**kwargs):
        year = int(kwargs['start_date'][:4]); calls.append(year)
        return transform.normalize_response(response(datetime(year,10,1,tzinfo=timezone.utc),100),[cell()])
    monkeypatch.setattr(extract,'request',fetch)
    extract.history(settings,[cell()],{'grid_id':'test'})
    result = extract.history(replace(settings,history_end_year=2025),[cell()],{'grid_id':'test'})
    assert calls==[2024,2025]
    assert result['ready_stations']==1
    assert result['stations'][0]['history_end_year']==2025

def test_citywide_layer_keeps_missing_history_unknown():
    result = transform.layer(forecast(),{'stations':[],'ready_stations':0})
    assert result['features'][0]['properties']['status']=='insufficient_history'

def test_24h_total_does_not_treat_missing_hour_as_zero():
    f = forecast()
    assert transform.layer(f,history())['features'][0]['properties']['forecast_24h_mm']==48
    del f['stations'][0]['hourly'][10]
    assert transform.layer(f,history())['features'][0]['properties']['forecast_24h_mm'] is None

def test_scheduler_failure_keeps_last_success_and_does_not_leak_error(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    path = tmp_path/'boundary.json'; write_json(path,{'type':'Feature','geometry':mapping(box(106.7,10.7,106.8,10.8))})
    monkeypatch.setenv('HCMC_BOUNDARY',str(path))
    service = Service()
    monkeypatch.setattr(service,'job_forecast',lambda:{'features':1})
    assert service.execute('forecast')
    saved = service.status['jobs']['forecast']['last_success_at']
    def fail(): raise RuntimeError('password must not leak')
    monkeypatch.setattr(service,'job_forecast',fail)
    assert not service.execute('forecast')
    status = read_json(service.status_path)
    assert status['jobs']['forecast']['last_success_at']==saved
    assert 'password' not in json.dumps(status)

def test_leader_lock_prevents_duplicate_snapshot_services(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path)); monkeypatch.delenv('DATABASE_URL',raising=False)
    with leader_lock():
        with pytest.raises((OSError,RuntimeError)):
            with leader_lock(): pass

def test_satellite_streams_multiple_windows_without_double_count(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from src.pipelines.flood_satellite.transform import observed_features
    path = tmp_path/'flood.tif'
    with rasterio.open(path,'w',driver='GTiff',width=2050,height=2,count=1,dtype='uint8',
                       crs=4326,transform=from_origin(106.7,10.8,0.00001,0.00001),nodata=255) as raster:
        raster.write(np.ones((2,2050),dtype='uint8'),1)
    features,counts = observed_features(path,None,box(106.699,10.799,106.73,10.801),
        {'id':'fixture','properties':{'datetime':'2026-10-01T00:00:00Z'},
         'assets':{'ensemble_flood_extent':{'href':'fixture'}}})
    assert counts['flood_pixels']==4100 and len(features)==3

def test_satellite_cache_reuses_scene_but_invalidates_changed_source(tmp_path,monkeypatch):
    from src.pipelines.flood_satellite import transform as satellite
    monkeypatch.setenv('DATA_DIR',str(tmp_path))
    calls = []
    def process(*args):
        calls.append(1)
        return [],{'valid_pixels':10,'flood_pixels':0,'excluded_pixels':0}
    monkeypatch.setattr(satellite,'observed_features',process)
    record = {'item':{'id':'scene','properties':{'datetime':'2026-10-01T00:00:00Z'},
                     'assets':{'ensemble_flood_extent':{'href':'fixture'}}},
              'paths':{'ensemble_flood_extent':tmp_path/'flood.tif'},
              'provenance':[{'url':'fixture','sha256':'a'*64}]}
    boundary = box(106.7,10.7,106.8,10.8)
    satellite.run([record],boundary); satellite.run([record],boundary)
    assert len(calls)==1
    record['provenance'][0]['sha256']='b'*64
    satellite.run([record],boundary)
    assert len(calls)==2
