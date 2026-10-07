from fastapi.testclient import TestClient
from app.main import app
from src.shared.data_io import write_json
from src.shared.database import publish
from shapely.geometry import box,mapping

def test_weather_and_service_status_api(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path)); monkeypatch.delenv('WAREHOUSE_PASSWORD',raising=False); monkeypatch.delenv('DATABASE_URL',raising=False)
    api = TestClient(app)
    assert api.get('/api/v1/weather/rain').status_code==503
    publish('rainwater',{'type':'FeatureCollection','features':[{'type':'Feature','id':'one',
        'geometry':mapping(box(106.7,10.7,106.8,10.8)),'properties':{'status':'insufficient_history'}}],
        'metadata':{'scope':'expanded','expires_at':'2020-01-01T00:00:00Z'}})
    result = api.get('/api/v1/weather/rain').json()
    assert result['metadata']['stale'] is True
    write_json(tmp_path/'etl/khoi-service-status.json',{'jobs':{'forecast':{'state':'failed'}}})
    assert api.get('/api/v1/etl/status').json()['jobs']['forecast']['state']=='failed'
    assert api.get('/api/v1/weather/rain/unknown').status_code==503
