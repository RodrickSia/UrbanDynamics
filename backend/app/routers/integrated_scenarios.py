import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
import psycopg
from threading import BoundedSemaphore
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.services.simulation.engine import polygon_and_area
from app.services.simulation.models import PolygonInput
from app.services.simulation.integrated.engine import predict, recommend, VERSION
from app.services.simulation.integrated.library import parameters, USES
from app.services.simulation.integrated.models import IntegratedRequest, RecommendationRequest
from app.services.simulation.integrated.solvers import SolverUnavailable
from app.services.simulation.store import load, save, StorageUnavailable

router = APIRouter(tags=["integrated-scenarios"])
slots = BoundedSemaphore(2)


def demo_payload(use="residential"):
    site = {"type": "Polygon", "coordinates": [[[106.76, 10.82], [106.761, 10.82],
              [106.761, 10.821], [106.76, 10.821], [106.76, 10.82]]]}
    footprint = {"type": "Polygon", "coordinates": [[[106.7603, 10.8203], [106.7607, 10.8203],
                    [106.7607, 10.8207], [106.7603, 10.8207], [106.7603, 10.8203]]]}
    area = polygon_and_area(PolygonInput(**site))[1]
    roof = polygon_and_area(PolygonInput(**footprint))[1]
    return {"title": "Chung cư tại Thủ Đức" if use == "residential" else f"Thủ Đức — {use}", "site": site,
            "development": {"buildings": [{"name": "Pilot building", "use": use, "footprint": footprint,
                "floors": 12 if use == "residential" else 4, "height_m": 36 if use == "residential" else 14,
                "units": 200 if use == "residential" else 0, "residents": 600 if use == "residential" else 0,
                "staff": 12 if use == "residential" else 100, "daily_visitors": 80,
                "daily_users": 600 if use == "school" else 200 if use == "hospital" else 0,
                "service_capacity": 600 if use in ("school", "hospital") else 0}],
                "paved_m2": area*.7-roof, "green_m2": area*.2, "permeable_m2": area*.1,
                "parking_spaces": 200, "ev_chargers": 12 if use == "residential" else 0,
                "trees": [{"longitude": 106.76015, "latitude": 10.82015, "canopy_radius_m": 5, "height_m": 8}]},
            "conditions": {"level": "base", "seed": 2026, "solar_date": "2026-04-15"}}


@router.get("/simulation/integrated", include_in_schema=False)
def integrated_page():
    return FileResponse(Path(__file__).resolve().parents[1]/"static"/"integrated.html")


@router.get("/simulation/integrated.js", include_in_schema=False)
def integrated_script():
    return FileResponse(Path(__file__).resolve().parents[1]/"static"/"integrated.js", media_type="text/javascript")


@router.get("/api/v1/scenarios/integrated/presets")
def presets():
    return {"default": demo_payload(), "building_presets": {use: demo_payload(use) for use in USES},
            "library": parameters("base"), "baseline_note": "Synthetic vacant parcel unless user supplies baseline with source"}


def run(operation):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Simulation workers busy; retry later")
    try:
        return save(operation())
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except SolverUnavailable as error:
        raise HTTPException(503, str(error)) from None
    except StorageUnavailable:
        raise HTTPException(503, "Scenario storage unavailable; result was not saved") from None
    except psycopg.Error:
        raise HTTPException(503, "Simulation context warehouse unavailable") from None
    finally:
        slots.release()


@router.post("/api/v1/scenarios/integrated/predict", status_code=201)
def prediction(body: IntegratedRequest):
    return run(lambda: predict(body))


def find(identifier):
    try:
        document = load(identifier)
    except StorageUnavailable:
        raise HTTPException(503, "Scenario storage unavailable") from None
    if document is None:
        raise HTTPException(404, "Scenario not found")
    if document.get("workflow") != "integrated_building_impact":
        raise HTTPException(409, "Use an integrated scenario run")
    return document


@router.get("/api/v1/scenarios/integrated/{identifier}")
def get_run(identifier: UUID):
    return find(identifier)


@router.post("/api/v1/scenarios/integrated/{identifier}/recommendations", status_code=201)
def suggestions(identifier: UUID, body: RecommendationRequest):
    source = find(identifier)
    if source['model_version'] != VERSION:
        raise HTTPException(409, "Stored run uses another model version; create a new prediction before recommendations")
    return run(lambda: recommend(source, body))


@router.get("/api/v1/scenarios/integrated/{identifier}/artifacts")
def artifacts(identifier: UUID):
    document = find(identifier)
    root = Path(os.getenv("SIMULATION_WORK_DIR", str(Path(tempfile.gettempdir())/"urban-dynamics-solvers"))).resolve()
    states = list(document["variants"].values())+[r["predicted"] for r in document["recommendations"]]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("scenario.json", json.dumps(document, ensure_ascii=False, allow_nan=False))
        for state in states:
            for engine in ("traffic", "drainage"):
                manifest = state[engine]["artifacts"]
                directory = (root/manifest["artifact_id"]).resolve()
                if directory.parent != root:
                    raise HTTPException(409, "Invalid artifact reference")
                if not directory.is_dir():
                    raise HTTPException(410, "Engine artifacts no longer retained; scenario JSON remains available")
                for name in manifest["files"]:
                    file = (directory/name).resolve()
                    if file.parent != directory or not file.is_file():
                        raise HTTPException(410, "Engine artifacts incomplete")
                    archive.write(file, f"{directory.name}/{file.name}")
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="integrated-{identifier}.zip"'})
