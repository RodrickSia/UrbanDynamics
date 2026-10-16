from fastapi import APIRouter, HTTPException, Query
from app.services import goong_places

router = APIRouter(prefix='/api/v1/places', tags=['places'])


@router.get('/search')
def search(q: str = Query(min_length=3,max_length=160)):
    try:
        return goong_places.search(q)
    except ValueError as error:
        raise HTTPException(503,str(error)) from None


@router.get('/detail')
def detail(place_id: str = Query(min_length=1,max_length=2000)):
    try:
        return goong_places.detail(place_id)
    except ValueError as error:
        raise HTTPException(503,str(error)) from None
