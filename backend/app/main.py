from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.routers import layers, floods, land_prices, scenarios, building_scenarios, weather, integrated_scenarios
from app.repository import readiness

app = FastAPI(title="UrbanDynamics API")


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, error):
    # Do not echo arbitrary input: NaN/Infinity cannot be serialized as JSON,
    # and submitted fields may contain private data.
    return JSONResponse(status_code=422, content={"detail": [
        {"type": item["type"], "loc": list(item["loc"]), "msg": item["msg"]}
        for item in error.errors()
    ]})


for router in (layers.router, floods.router, land_prices.router, scenarios.router, building_scenarios.router, weather.router, integrated_scenarios.router):
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
    if status["loaded_layers"] == 0:
        raise HTTPException(503, "No layers loaded")
    return {"status": "ready", **status}
