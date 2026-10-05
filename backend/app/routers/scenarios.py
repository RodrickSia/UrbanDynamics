from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.repository import LayerUnavailable
from app.services.rain_scenario import run

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


class RainScenario(BaseModel):
    rain_3h_mm: float = Field(ge=0, le=1000, allow_inf_nan=False)
    radius_m: int = Field(default=250, ge=1, le=2000)
    polygon: dict | None = None


@router.post("/rain")
def rain_scenario(body: RainScenario):
    try:
        return run(body.rain_3h_mm, body.radius_m, body.polygon)
    except (FileNotFoundError, LayerUnavailable):
        raise HTTPException(
            503, "Need flood_history and rainfall input snapshots"
        ) from None
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            400, "Invalid scenario geometry or rainfall input"
        ) from None
