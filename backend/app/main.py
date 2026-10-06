from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.repository import readiness
from app.routers import floods, land_prices, layers, population, scenarios, urban

app = FastAPI(
    title="UrbanDynamics Data API",
    summary="Map-ready population, flood, and reviewed land-price data from PostGIS.",
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

for router in (
    layers.router,
    floods.router,
    land_prices.router,
    population.router,
    scenarios.router,
    urban.router,
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
        },
    }
