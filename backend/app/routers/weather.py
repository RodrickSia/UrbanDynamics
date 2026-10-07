from fastapi import APIRouter,Query,HTTPException
from app import repository
from app.routers.layers import get_features
from src.shared.data_io import read_json
from src.pipelines.rainwater.load import input_pair

router = APIRouter(prefix='/api/v1',tags=['weather and ETL'])

@router.get('/weather/rain')
def rain(bbox:str|None=None,limit:int=Query(5000,ge=1,le=10000)):
    return get_features('rainwater',bbox,limit=limit)

@router.get('/weather/rain/{station_id}')
def hourly(station_id:str):
    try:
        forecast,history = input_pair(repository.directory())
        station = next((s for s in forecast['stations'] if s['id']==station_id),None)
        if station is None: raise HTTPException(404,'Unknown weather station')
        return {'station':station,'history':next((s for s in history['stations'] if s['id']==station_id),None),
                'metadata':repository.freshness({k:v for k,v in forecast.items() if k!='stations'})}
    except (FileNotFoundError,ValueError,KeyError,OSError):
        raise HTTPException(503,'Weather inputs unavailable') from None

@router.get('/etl/status')
def etl_status():
    try: return read_json(repository.directory()/'etl/khoi-service-status.json')
    except (FileNotFoundError,ValueError,OSError): raise HTTPException(503,'ETL service has not run') from None
