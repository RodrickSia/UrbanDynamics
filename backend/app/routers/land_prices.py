import json

from fastapi import APIRouter, HTTPException, Query

from app.repository import directory

from .layers import get_features

router = APIRouter(prefix="/api/v1", tags=["land prices"])


@router.get("/land-prices")
def prices(bbox: str | None = None, limit: int = Query(5000, ge=1, le=10000)):
    return get_features("land_price", bbox, limit=limit)


@router.get("/land-prices/rows")
def price_rows():
    path = directory() / "review" / "land_price_rows.json"
    if not path.exists():
        raise HTTPException(503, "Official price rows not loaded")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(503, "Official price rows unavailable or invalid") from None
