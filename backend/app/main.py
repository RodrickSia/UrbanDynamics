from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.repository import readiness
from app.routers import (
    area_indicators,
    building_scenarios,
    floods,
    integrated_scenarios,
    land_prices,
    layers,
    parcels,
    planning_scenarios,
    planning_system_demo,
    population,
    scenarios,
    traffic,
    traffic_sumo,
    urban,
    weather,
    zoning,
)

app = FastAPI(
    title="UrbanDynamics Data API",
    summary=(
        "Map-ready population, building, flood, and official reference-price data from PostGIS."
    ),
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
)
if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, error):
    # Do not echo arbitrary input: NaN/Infinity cannot be serialized as JSON,
    # and submitted fields may contain private data.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"type": item["type"], "loc": list(item["loc"]), "msg": item["msg"]}
                for item in error.errors()
            ]
        },
    )


for router in (
    area_indicators.router,
    zoning.router,
    parcels.router,
    layers.router,
    floods.router,
    land_prices.router,
    population.router,
    scenarios.router,
    urban.router,
    building_scenarios.router,
    weather.router,
    integrated_scenarios.router,
    planning_scenarios.router,
    planning_scenarios.preview_router,
    planning_system_demo.router,
    traffic.router,
    traffic_sumo.router,
):
    app.include_router(router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready():
    try:
        status = readiness()
    except Exception:
        raise HTTPException(503, "Data storage not ready") from None
    if status["loaded_layers"] == 0 and status["loaded_population_years"] == 0:
        raise HTTPException(503, "No map data loaded")
    return {"status": "ready", **status}


@app.get("/api/v1", tags=["discovery"])
def api_index():
    return {
        "name": "UrbanDynamics Data API",
        "version": app.version,
        "docs": "/api/v1/docs",
        "openapi": "/api/v1/openapi.json",
        "endpoints": {
            "layers": "/api/v1/layers",
            "vector_features": "/api/v1/layers/{layer}/features",
            "vector_tiles": "/api/v1/layers/{layer}/tiles/{z}/{x}/{y}.pbf",
            "population": "/api/v1/population",
            "urban_flood": "/api/v1/urban/flood",
            "urban_land_price": "/api/v1/urban/land-price",
            "floods": "/api/v1/floods/{history,satellite,risk}",
            "land_prices": "/api/v1/land-prices",
            "traffic_prediction": "/api/v1/traffic/prediction?weekday=1&period=08:00",
            "sumo_network": "/api/v1/traffic/network",
            "sumo_congestion_simulations": "/api/v1/traffic/sumo-simulations/runs",
        },
    }
