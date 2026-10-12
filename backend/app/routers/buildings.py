"""GBA LoD1 building coverage and vector tiles for the 3D map."""

from fastapi import APIRouter, HTTPException, Response
from psycopg import Error as DatabaseError
from src.shared.database import warehouse_configured

from app.services import buildings

router = APIRouter(prefix="/api/v1/buildings", tags=["buildings"])


@router.get("/snapshot")
def snapshot():
    if not warehouse_configured():
        raise HTTPException(503, "Building model requires the PostGIS warehouse")
    try:
        result = buildings.snapshot()
    except (OSError, DatabaseError):
        raise HTTPException(503, "Building model unavailable") from None
    if result is None:
        raise HTTPException(404, "GBA LoD1 building model has not been loaded")
    return {"source": "hcmc_gba_lod1", **result}


@router.get("/tiles/{z}/{x}/{y}.pbf")
def vector_tile(z: int, x: int, y: int):
    if not 0 <= z <= buildings.MAX_NATIVE_ZOOM or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "Tile coordinates are outside the XYZ matrix")
    if not warehouse_configured():
        raise HTTPException(503, "Building model requires the PostGIS warehouse")
    try:
        tile = buildings.vector_tile(z, x, y)
    except (OSError, DatabaseError):
        raise HTTPException(503, "Building tiles unavailable") from None
    if not tile:
        return Response(status_code=204, headers={"Cache-Control": "public, max-age=300"})
    return Response(tile, media_type="application/vnd.mapbox-vector-tile",
                    headers={"Cache-Control": "public, max-age=300"})
