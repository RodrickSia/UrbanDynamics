"""Standalone SUMO traffic-congestion scenarios; independent of planning studies."""

from datetime import time
from uuid import UUID

from fastapi import APIRouter, HTTPException
from src.shared.database import connect_to_warehouse

from app.services import traffic_sumo_prediction as prediction

router = APIRouter(prefix="/api/v1/traffic/sumo-simulations", tags=["SUMO traffic simulations"])


@router.get("/catalog")
def simulation_catalog():
    return prediction.catalog()


@router.get("/latest")
def get_latest_scenario():
    try:
        cached = prediction.latest_cached_scenario()
    except Exception:
        raise HTTPException(
            503, "SUMO scenario cache unavailable; apply database migrations"
        ) from None
    if cached is None:
        raise HTTPException(404, "No precomputed one-hour SUMO scenario is available")
    return {**cached, "status": "completed", "cached": True}


@router.get("/scenarios/{weekday}/{period}")
def get_cached_scenario(weekday: int, period: str):
    if not 1 <= weekday <= 7:
        raise HTTPException(422, "weekday must be between 1 (Monday) and 7 (Sunday)")
    try:
        parsed_period = time.fromisoformat(period)
    except ValueError:
        raise HTTPException(422, "period must be a time such as 08:00 or 08:30") from None
    if parsed_period.minute not in (0, 30) or parsed_period.second or parsed_period.microsecond:
        raise HTTPException(422, "period must be on a 30-minute boundary")
    try:
        cached = prediction.cached_scenario(weekday, parsed_period.strftime("%H:%M"))
    except Exception:
        raise HTTPException(
            503, "SUMO scenario cache unavailable; apply database migrations"
        ) from None
    if cached is None:
        raise HTTPException(404, "SUMO scenario has not been precomputed")
    return {**cached, "status": "completed", "cached": True}


@router.get("/runs/{run_id}")
def get_run(run_id: UUID):
    try:
        with connect_to_warehouse() as connection:
            row = connection.execute(
                """
                SELECT status, weekday, period, metadata, error, created_at, updated_at
                FROM transport.sumo_congestion_run WHERE run_id = %s
            """,
                (run_id,),
            ).fetchone()
    except Exception:
        raise HTTPException(503, "SUMO prediction queue unavailable") from None
    if row is None:
        raise HTTPException(404, "SUMO traffic simulation run not found")
    return {
        "run_id": str(run_id),
        "status": row[0],
        "weekday": row[1],
        "period": row[2].strftime("%H:%M"),
        "metadata": row[3],
        "error": row[4],
        "created_at": row[5],
        "updated_at": row[6],
    }


@router.get("/runs/{run_id}/features")
def get_run_features(run_id: UUID):
    status = get_run(run_id)
    if status["status"] != "completed":
        raise HTTPException(409, "SUMO simulation has not completed")
    result = prediction.read_result(str(run_id))
    if result is None:
        result = prediction.read_cached_result(str(run_id))
    if result is None:
        raise HTTPException(404, "SUMO traffic simulation result file is missing")
    return result
