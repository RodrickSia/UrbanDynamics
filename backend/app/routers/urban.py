"""Frontend-friendly aliases for datasets currently published by the ETL."""

from datetime import datetime

from fastapi import APIRouter, Query

from app.routers.layers import get_features
from app.routers.population import catalog as population_catalog

router = APIRouter(prefix="/api/v1/urban", tags=["urban layers"])


@router.get("/population")
def population():
    """Return the population raster catalog and its map tile templates."""
    return population_catalog()


@router.get("/flood")
def flood(
    bbox: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    """Return the ETL's rainfall-threshold indicators as GeoJSON."""
    return get_features("flood_risk", bbox, start, end, limit)


@router.get("/land-price")
def land_price(bbox: str | None = None, limit: int = Query(5000, ge=1, le=10000)):
    """Return official reference-price road segments with matching provenance."""
    return get_features("land_price", bbox, limit=limit)
