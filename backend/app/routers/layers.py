import math
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from psycopg import Error as DatabaseError
from app import repository

router = APIRouter(prefix="/api/v1", tags=["layers"])

def get_features(layer, bbox=None, start=None, end=None, limit=5000):
    if layer not in repository.LAYERS:
        raise HTTPException(404, "Unknown layer")
    bounds = None
    try:
        if bbox:
            bounds = tuple(float(n) for n in bbox.split(","))
            if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
                raise ValueError()
            west, south, east, north = bounds
            if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                raise ValueError()
        start = repository.instant(start.isoformat()) if start else None
        end = repository.instant(end.isoformat()) if end else None
        if start and end and start >= end:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "Invalid WGS84 bbox or time interval") from None
    try:
        return repository.features(layer, bounds, start, end, limit)
    except repository.LayerUnavailable:
        raise HTTPException(503, "Layer not loaded; run its ETL pipeline") from None
    except (OSError, ValueError, DatabaseError):
        raise HTTPException(503, "Layer snapshot unavailable or invalid") from None

@router.get("/layers")
def layer_catalog():
    result = []
    for layer in repository.LAYERS:
        try:
            result.append({"id": layer, "available": True, **repository.metadata(layer)})
        except repository.LayerUnavailable:
            result.append({"id": layer, "available": False})
        except (OSError, ValueError, DatabaseError):
            raise HTTPException(503, "Layer storage unavailable") from None
    return {"layers": result}

@router.get("/layers/{layer}/features")
def layer_features(layer: str, bbox: str | None = None, start: datetime | None = None,
                   end: datetime | None = None, limit: int = Query(5000, ge=1, le=10000)):
    return get_features(layer, bbox, start, end, limit)
