from datetime import datetime

from fastapi import APIRouter, Query

from .layers import get_features

router = APIRouter(prefix="/api/v1/floods", tags=["floods"])


@router.get("/history")
def history(
    bbox: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    return get_features("flood_history", bbox, start, end, limit)


@router.get("/satellite")
def satellite(
    bbox: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    return get_features("flood_satellite", bbox, start, end, limit)


@router.get("/risk")
def risk(bbox: str | None = None, limit: int = Query(5000, ge=1, le=10000)):
    return get_features("flood_risk", bbox, limit=limit)
