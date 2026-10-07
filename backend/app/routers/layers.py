import math
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
from psycopg import Error as DatabaseError
from src.shared.database import warehouse_configured

from app import repository

router = APIRouter(prefix="/api/v1", tags=["layers"])


def get_features(layer, bbox=None, start=None, end=None, limit=5000):
    if layer not in repository.LAYERS:
        raise HTTPException(404, "Unknown layer")
    if (start or end) and not repository.LAYER_INFO[layer]["time_enabled"]:
        raise HTTPException(400, "Time filtering is not supported for this layer")
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
            result.append(
                {
                    "id": layer,
                    **repository.LAYER_INFO[layer],
                    "available": True,
                    **repository.metadata(layer),
                }
            )
        except repository.LayerUnavailable:
            result.append({"id": layer, **repository.LAYER_INFO[layer], "available": False})
        except (OSError, ValueError, DatabaseError):
            raise HTTPException(503, "Layer storage unavailable") from None
    return {"layers": result}


@router.get("/layers/{layer}/features")
def layer_features(
    layer: str,
    bbox: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    return get_features(layer, bbox, start, end, limit)


@router.get("/layers/{layer}/tilejson.json")
def layer_tilejson(layer: str, request: Request):
    if layer not in repository.LAYERS:
        raise HTTPException(404, "Unknown layer")
    try:
        metadata = repository.metadata(layer)
    except repository.LayerUnavailable:
        raise HTTPException(404, "Layer has not been loaded") from None
    except (OSError, ValueError, DatabaseError):
        raise HTTPException(503, "Layer storage unavailable") from None
    return {
        "tilejson": "3.0.0",
        "name": layer,
        "scheme": "xyz",
        "tiles": [
            f"{str(request.base_url).rstrip('/')}/api/v1/layers/{layer}/tiles/{{z}}/{{x}}/{{y}}.pbf"
            + ("?schema=2" if layer in ("flood_history", "parcels") else "")
        ],
        "minzoom": 12 if layer == 'parcels' else 0,
        "maxzoom": 16 if layer == 'parcels' else 18,
        "vector_layers": [{"id": "features", "fields": repository.LAYER_INFO[layer]["fields"]}],
        "metadata": metadata,
    }


@router.get("/layers/{layer}/tiles/{z}/{x}/{y}.pbf")
def layer_vector_tile(
    layer: str,
    z: int,
    x: int,
    y: int,
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
):
    if layer not in repository.LAYERS:
        raise HTTPException(404, "Unknown layer")
    if not warehouse_configured():
        raise HTTPException(503, "Vector tiles require the PostGIS warehouse")
    if not 0 <= z <= 18 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "Tile coordinates are outside the XYZ matrix")
    if start and end and start >= end:
        raise HTTPException(400, "start must be earlier than end")
    if (start or end) and not repository.LAYER_INFO[layer]["time_enabled"]:
        raise HTTPException(400, "Time filtering is not supported for this layer")
    try:
        snapshot = repository.metadata(layer)
        tile = repository.vector_tile(layer, z, x, y, start, end)
    except repository.LayerUnavailable:
        raise HTTPException(404, "Layer has not been loaded") from None
    except DatabaseError:
        raise HTTPException(503, "Vector tile storage unavailable") from None
    if not tile:
        return Response(status_code=204, headers={"Cache-Control": "public, max-age=300"})
    updated = snapshot.get("updated_at", snapshot.get("ingested_at", "unknown"))
    schema = "v2-" if layer in ('flood_history', 'parcels') else ""
    etag = f'W/"{schema}{layer}-{updated}-{start or "all"}-{end or "all"}-{z}-{x}-{y}"'
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=300"}
        )
    return Response(
        tile,
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "public, max-age=300", "ETag": etag},
    )
