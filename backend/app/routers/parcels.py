from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response
from psycopg import Error as DatabaseError

from app.services import parcels

router = APIRouter(prefix='/api/v1/parcels', tags=['parcels'])


@router.get('/{parcel_id}')
def parcel_detail(parcel_id: Annotated[int, Path(ge=1, le=9223372036854775807)], response: Response):
    try:
        result = parcels.detail(parcel_id)
    except (OSError, ValueError, DatabaseError):
        raise HTTPException(503, 'Parcel details temporarily unavailable') from None
    if result is None:
        raise HTTPException(404, 'Parcel not found')
    response.headers['Cache-Control'] = 'public, max-age=300'
    return result
