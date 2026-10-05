from fastapi import FastAPI, HTTPException
from app.routers import layers, floods, land_prices, scenarios
from app.repository import readiness

app = FastAPI(title="UrbanDynamics API")
for router in (layers.router, floods.router, land_prices.router, scenarios.router):
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
