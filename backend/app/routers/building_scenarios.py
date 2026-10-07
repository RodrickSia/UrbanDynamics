from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.simulation.engine import calculate, polygon_and_area
from app.services.simulation.models import BuildingScenario, BuildingPrediction, ImprovementConstraints, PolygonInput
from app.services.simulation.prediction import predict, recommend
from app.services.simulation.store import StorageUnavailable, load, save

router = APIRouter(tags=["building-scenarios"])


@router.get("/simulation", include_in_schema=False)
def simulation_page():
    return FileResponse(Path(__file__).resolve().parents[1] / "static" / "simulation.html")


@router.get("/simulation.js", include_in_schema=False)
def simulation_script():
    return FileResponse(Path(__file__).resolve().parents[1] / "static" / "simulation.js",
                        media_type="text/javascript")


@router.post("/api/v1/scenarios/site-area")
def site_area(body: PolygonInput):
    try:
        _, area = polygon_and_area(body)
        return {"area_m2": area, "method": "WGS84 ellipsoidal area", "units": "m2"}
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.post("/api/v1/scenarios/building", status_code=201)
def building_scenario(body: BuildingScenario):
    try:
        result = calculate(body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    try:
        return save(result)
    except StorageUnavailable:
        raise HTTPException(503, "Scenario storage unavailable; result was not saved") from None


@router.post("/api/v1/scenarios/building/predict", status_code=201)
def predict_building(body: BuildingPrediction):
    try:
        return save(predict(body))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except StorageUnavailable:
        raise HTTPException(503, "Scenario storage unavailable; result was not saved") from None


@router.post("/api/v1/scenarios/building/{identifier}/recommendations", status_code=201)
def recommend_building(identifier: UUID, body: ImprovementConstraints):
    try:
        source = load(identifier)
        if source is None:
            raise HTTPException(404, "Scenario not found")
        if source.get("workflow") != "predict_assess_recommend":
            raise HTTPException(409, "Run the prediction workflow before requesting suggestions")
        return save(recommend(source, body))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except StorageUnavailable:
        raise HTTPException(503, "Scenario storage unavailable; result was not saved") from None


@router.get("/api/v1/scenarios/building/{identifier}")
def building_result(identifier: UUID):
    try:
        result = load(identifier)
    except StorageUnavailable:
        raise HTTPException(503, "Scenario storage unavailable") from None
    if result is None:
        raise HTTPException(404, "Scenario not found")
    return result
