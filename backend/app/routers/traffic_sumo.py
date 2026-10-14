"""Standalone SUMO traffic-congestion scenarios; independent of planning studies."""

from datetime import time
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field
from src.shared.database import connect_to_warehouse

from app.services import traffic_sumo_prediction as prediction

router = APIRouter(prefix="/api/v1/traffic/sumo-simulations", tags=["SUMO traffic simulations"])


class RunRequest(BaseModel):
    weekday: int = Field(ge=1, le=7, description="ISO weekday; Monday=1")
    period: time


@router.get("/catalog")
def simulation_catalog():
    return prediction.catalog()


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


@router.post("/runs")
def create_run(request: RunRequest):
    if request.period.minute not in (0, 30) or request.period.second or request.period.microsecond:
        raise HTTPException(422, "period must be on a 30-minute boundary, such as 08:00 or 08:30")
    try:
        cached = prediction.cached_scenario(request.weekday, request.period.strftime("%H:%M"))
    except Exception:
        raise HTTPException(
            503, "SUMO scenario cache unavailable; apply database migrations"
        ) from None
    if cached is not None:
        return {**cached, "status": "completed", "cached": True}
    if not prediction.catalog()["available"]:
        raise HTTPException(
            503,
            "SUMO prediction needs the HCMC OSM input and matched traffic observations",
        )
    run_id = uuid4()
    try:
        with connect_to_warehouse() as connection:
            connection.execute(
                """
                INSERT INTO transport.sumo_congestion_run (run_id, weekday, period, status)
                VALUES (%s, %s, %s, 'queued')
            """,
                (run_id, request.weekday, request.period),
            )
    except UniqueViolation:
        with connect_to_warehouse() as connection:
            active = connection.execute(
                """
                SELECT run_id, status, metadata
                FROM transport.sumo_congestion_run
                WHERE weekday = %s AND period = %s AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (request.weekday, request.period),
            ).fetchone()
        if active is None:
            raise HTTPException(409, "A SUMO traffic run is already queued or running") from None
        return {
            "run_id": str(active[0]),
            "status": active[1],
            "metadata": active[2],
            "cached": False,
        }
    except Exception:
        raise HTTPException(
            503, "SUMO prediction queue unavailable; apply database migrations"
        ) from None
    return {"run_id": str(run_id), "status": "queued"}


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
