"""Population raster discovery, sampling, statistics and XYZ map tiles."""

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from psycopg import Error as DatabaseError
from src.shared.database import warehouse_configured

from app import repository
from app.services.raster_tiles import render_population_tile

router = APIRouter(prefix="/api/v1/population", tags=["population"])
MAX_ZOOM = 18
PALETTE_LEGEND = {
    "pseudocolor": {
        "description": "Fixed person-per-cell intervals, interpolated between these stops.",
        "unit": "persons per 100 m population cell",
        "stops": [0, 1, 10, 50, 100, 500, 1000],
    },
    "greyscale": {
        "description": "Fixed grayscale person-per-cell intervals.",
        "unit": "persons per 100 m population cell",
        "stops": [0, 1, 10, 100, 1000],
    },
    "fire": {
        "description": "Fixed fire-color person-per-cell intervals.",
        "unit": "persons per 100 m population cell",
        "stops": [0, 1, 10, 50, 100, 1000],
    },
}


def require_warehouse():
    if not warehouse_configured():
        raise HTTPException(503, "Population map services require the PostGIS warehouse")


def validate_tile(z: int, x: int, y: int):
    if not 0 <= z <= MAX_ZOOM or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "Tile coordinates are outside the XYZ matrix")


def has_year(year: int):
    try:
        years = repository.population_years()
    except DatabaseError:
        raise HTTPException(503, "Population raster storage unavailable") from None
    if not any(item["year"] == year for item in years):
        raise HTTPException(404, f"No population raster is loaded for {year}")
    return next(item for item in years if item["year"] == year)


@router.get("")
def catalog():
    """Describe the stored WorldPop rasters and their units and map endpoints."""
    require_warehouse()
    try:
        years = repository.population_years()
    except DatabaseError:
        raise HTTPException(503, "Population raster storage unavailable") from None
    return {
        "id": "population",
        "title": "WorldPop Vietnam constrained population estimates",
        "available": bool(years),
        "years": years,
        "unit": "persons per source raster cell",
        "source_resolution": "100 m nominal resolution",
        "crs": "EPSG:4326",
        "tile_url": "/api/v1/population/{year}/tiles/{z}/{x}/{y}.png",
        "statistics_url": "/api/v1/population/{year}/stats?bbox=west,south,east,north",
        "value_url": "/api/v1/population/{year}/value?lng=longitude&lat=latitude",
        "palettes": PALETTE_LEGEND,
    }


@router.get("/years")
def years():
    """List years actually loaded, with tile counts, source files and load time."""
    require_warehouse()
    try:
        return {"years": repository.population_years()}
    except DatabaseError:
        raise HTTPException(503, "Population raster storage unavailable") from None


@router.get("/{year}/tilejson.json")
def tilejson(request: Request, year: int = Path(ge=1900, le=2200)):
    require_warehouse()
    source = has_year(year)
    return {
        "tilejson": "3.0.0",
        "name": f"WorldPop {year}",
        "scheme": "xyz",
        "tiles": [
            f"{str(request.base_url).rstrip('/')}/api/v1/population/{year}/tiles/"
            "{z}/{x}/{y}.png?palette=pseudocolor&render=2"
        ],
        "format": "png",
        "minzoom": 0,
        "maxzoom": MAX_ZOOM,
        "bounds": [102.0, 8.0, 110.0, 24.0],
        "metadata": {**source, "unit": "persons per source raster cell", "crs": "EPSG:4326"},
    }


@router.get("/{year}/tiles/{z}/{x}/{y}.png")
def tile(
    request: Request,
    year: int = Path(ge=1900, le=2200),
    z: int = Path(ge=0, le=MAX_ZOOM),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
    palette: str = Query("pseudocolor", pattern="^(pseudocolor|greyscale|fire)$"),
):
    require_warehouse()
    validate_tile(z, x, y)
    source = has_year(year)
    try:
        samples = repository.population_tile(year, z, x, y)
    except DatabaseError:
        raise HTTPException(503, "Population raster tile unavailable") from None
    if samples is None:
        return Response(status_code=204, headers={"Cache-Control": "public, max-age=86400"})
    content = render_population_tile(samples, palette)
    loaded_at = source["loaded_at"] or "unknown"
    etag = f'W/"population-v2-{year}-{loaded_at}-{palette}-{z}-{x}-{y}"'
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"Cache-Control": "public, max-age=86400", "ETag": etag},
        )
    return Response(
        content,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": etag,
        },
    )


@router.get("/{year}/value")
def value(
    year: int = Path(ge=1900, le=2200),
    lng: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
):
    require_warehouse()
    has_year(year)
    try:
        population = repository.population_value(year, lng, lat)
    except DatabaseError:
        raise HTTPException(503, "Population raster sampling unavailable") from None
    return {
        "year": year,
        "coordinates": [lng, lat],
        "population": population,
        "unit": "persons per source raster cell",
        "nodata": population is None,
    }


@router.get("/{year}/stats")
def statistics(
    year: int = Path(ge=1900, le=2200),
    bbox: str = Query(description="west,south,east,north in EPSG:4326"),
):
    require_warehouse()
    has_year(year)
    try:
        bounds = tuple(float(value) for value in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must contain four numeric WGS84 coordinates") from None
    if len(bounds) != 4:
        raise HTTPException(400, "bbox must contain west,south,east,north")
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(400, "bbox is outside WGS84 bounds or has inverted edges")
    if (east - west) * (north - south) > 4:
        raise HTTPException(400, "bbox is too large; request a smaller map viewport")
    try:
        stats = repository.population_statistics(year, bounds)
    except DatabaseError:
        raise HTTPException(503, "Population raster statistics unavailable") from None
    if stats is None or stats["pixel_count"] == 0:
        raise HTTPException(404, "No population pixels intersect this area")
    return {
        "year": year,
        "bbox": bounds,
        "unit": "persons per source raster cell",
        "statistics": stats,
        "note": (
            "Summary uses source raster pixels intersecting the viewport; it is not "
            "area-normalized population density."
        ),
    }
