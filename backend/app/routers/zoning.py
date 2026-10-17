from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from psycopg import Error as DatabaseError
from src.shared.database import warehouse_configured

from app.services import parcels
from pydantic import ValidationError
from shapely.errors import GEOSException

from app.services.zoning import baseline, development, engine, store
from app.services.zoning.indicators import report
from app.services.zoning.models import Command, PlanInput
from app.services.zoning.cost_models import CostSettings
from app.services.zoning import costs
from app.services.zoning.simulation import SimulationInput, SimulationRunInput, study_from_plan
from app.services.simulation.integrated.models import MapBuildingCollection

router = APIRouter(prefix="/api/v1/zoning/plans", tags=["zoning plans"])


def execute(operation):
    try:
        return operation()
    except store.Conflict as error:
        raise HTTPException(409, str(error)) from None
    except store.StorageUnavailable as error:
        raise HTTPException(503, str(error)) from None
    except ValidationError:
        raise HTTPException(422, "Check the required fields and numeric rule ranges") from None
    except (ValueError, GEOSException) as error:
        raise HTTPException(422, str(error)) from None
    except (KeyError, TypeError, AttributeError):
        raise HTTPException(422, "Invalid zoning command or geometry") from None


def require_plan(identifier):
    document = store.load(identifier)
    if document is None:
        raise HTTPException(404, "Plan not found")
    return document


@router.get("")
def list_plans():
    return execute(lambda: {"plans": store.listing()})


@router.post("", status_code=201)
def create_plan(data: PlanInput):
    return execute(lambda: engine.present(store.save_new(engine.create(data))))


@router.get("/{identifier}")
def get_plan(identifier: UUID):
    return execute(lambda: engine.present(require_plan(identifier)))


@router.delete("/{identifier}", status_code=204)
def delete_plan(identifier: UUID, revision: int = Query(ge=1)):
    if not execute(lambda: store.delete(identifier, revision)):
        raise HTTPException(404, "Plan not found")
    return Response(status_code=204)


@router.get("/{identifier}/parcels/tiles/{z}/{x}/{y}.pbf")
def plan_parcels_tile(identifier: UUID, z: int, x: int, y: int, revision: int = Query(ge=1)):
    if not 0 <= z <= 18 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "Tile coordinates are outside the XYZ matrix")
    plan = execute(lambda: require_plan(identifier))
    if plan["revision"] != revision:
        raise HTTPException(409, "Plan changed. Reload its parcels.")
    if not warehouse_configured():
        raise HTTPException(503, "Plan parcels require the PostGIS warehouse")
    try:
        tile = parcels.plan_vector_tile(plan["study_area"], z, x, y)
    except (OSError, ValueError, DatabaseError):
        raise HTTPException(503, "Plan parcels temporarily unavailable") from None
    return Response(tile, media_type="application/vnd.mapbox-vector-tile", status_code=200 if tile else 204,
                    headers={"Cache-Control": "private, max-age=300"})


@router.get("/{identifier}/zoned-parcels/tiles/{z}/{x}/{y}.pbf")
def zoned_parcels_tile(identifier: UUID, z: int, x: int, y: int,
                       revision: int = Query(ge=1), scenario_id: UUID = Query()):
    if not 0 <= z <= 18 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "Tile coordinates are outside the XYZ matrix")
    plan = execute(lambda: require_plan(identifier))
    if plan["revision"] != revision:
        raise HTTPException(409, "Plan changed. Reload its parcels.")
    scenario = next((item for item in plan["scenarios"] if item["id"] == str(scenario_id)), None)
    if scenario is None:
        raise HTTPException(404, "Scenario not found")
    if scenario["kind"] == "reference" or not scenario["zones"]:
        return Response(status_code=204)
    if not warehouse_configured():
        raise HTTPException(503, "Zoned parcels require the PostGIS warehouse")
    zones = [{"id": item["id"], "geometry": item["geometry"]} for item in scenario["zones"]]
    try:
        tile = parcels.zoned_parcel_vector_tile(zones, z, x, y)
    except (OSError, ValueError, DatabaseError):
        raise HTTPException(503, "Zoned parcels temporarily unavailable") from None
    return Response(tile, media_type="application/vnd.mapbox-vector-tile", status_code=200 if tile else 204,
                    headers={"Cache-Control": "private, max-age=300"})


@router.post("/{identifier}/commands")
def change_plan(identifier: UUID, command: Command):
    def change():
        def mutate(plan):
            if command.action in development.ACTIONS:
                engine.editable(plan, command.scenario_id)
                parcel_id = command.payload.get("parcel_id")
                if parcel_id:
                    parcel = selected_site(plan, str(parcel_id), command.scenario_id)
                    plan.setdefault("parcels", {})[parcel["id"]] = parcel
            return engine.apply(plan, command)
        result = store.update(identifier, command.revision, mutate)
        if result is None:
            raise HTTPException(404, "Plan not found")
        return engine.present(result)
    return execute(change)


@router.post("/{identifier}/preview")
def preview(identifier: UUID, command: Command):
    def calculate():
        plan = require_plan(identifier)
        if plan["revision"] != command.revision:
            raise store.Conflict("Plan changed. Reload before previewing edits.")
        if command.action in ("save_building", "generate_building"):
            scenario = engine.editable(plan, command.scenario_id)
            parcel = selected_site(plan, str(command.payload.get("parcel_id", "")), command.scenario_id)
            plan.setdefault("parcels", {})[parcel["id"]] = parcel
            operation = development.generate if command.action == "generate_building" else development.prepare_building
            building, report = operation(plan, scenario, command.payload)
            return {"building": building, "parcel": parcel, **report}
        if command.action not in ("draw", "reshape"):
            raise ValueError("Preview supports draw and reshape operations")
        scenario = engine.editable(plan, command.scenario_id)
        zones, summary = engine.boundary_change(plan, scenario, command.payload, plan["revision"] + 1)
        return {"zones": zones, **summary}
    return execute(calculate)


def selected_site(plan, site_id, scenario_id):
    if site_id.startswith('zone:'):
        scenario = engine.find(plan['scenarios'], scenario_id)
        return development.zone_site(plan, scenario, site_id)
    return selected_parcel(plan, site_id)


def selected_parcel(plan, parcel_id):
    if not parcel_id.isdigit() or not 0 < int(parcel_id) <= 9223372036854775807:
        raise ValueError("Invalid parcel ID")
    if parcel_id in plan.get("parcels", {}):
        return plan["parcels"][parcel_id]
    if not warehouse_configured():
        raise HTTPException(503, "Development parcels require the PostGIS warehouse")
    try:
        source = parcels.development_parcel(int(parcel_id))
    except (OSError, ValueError, DatabaseError):
        raise HTTPException(503, "Parcel geometry temporarily unavailable; retry") from None
    if not source:
        raise HTTPException(404, "Parcel not found")
    return development.parcel_snapshot(plan, source)


@router.get("/{identifier}/development/parcels/{parcel_id}")
def development_parcel(identifier: UUID, parcel_id: str, scenario_id: str):
    return parcel_development_report(identifier, parcel_id, scenario_id)


@router.post("/{identifier}/development/parcels/{parcel_id}/baseline")
def development_map_baseline(identifier: UUID, parcel_id: str, scenario_id: str, body: MapBuildingCollection):
    return parcel_development_report(identifier, parcel_id, scenario_id, body)


def parcel_development_report(identifier, parcel_id, scenario_id, map_buildings=None):
    def read():
        plan = require_plan(identifier)
        scenario = engine.find(plan["scenarios"], scenario_id)
        parcel = selected_site(plan, parcel_id, scenario_id)
        buildings = [b for b in scenario.get("buildings", []) if b["parcel_id"] == parcel_id]
        records = baseline.buildings(parcel, plan['study_area'])
        if map_buildings is not None:
            records = baseline.with_map_buildings(parcel, plan['study_area'], records, map_buildings)
        current = baseline.report(parcel, plan['study_area'], records)
        retained = [] if any(m['parcel_id'] == parcel_id for m in scenario.get('demolition_masks', [])) else records or []
        scenario_setback = development.minimum_setback(parcel, [*retained, *buildings])
        return {"parcel": parcel, "catalog": development.CATALOG,
                "baseline": current, "scenario_setback_m": scenario_setback,
                "zoning": baseline.zoning(plan, scenario, parcel), "scenario_kind": scenario['kind'],
                **development.validation(plan, scenario, parcel, buildings)}
    return execute(read)


@router.get("/{identifier}/indicators")
def indicators(identifier: UUID, scenario_id: str, compare_id: str | None = None):
    return execute(lambda: report(require_plan(identifier), scenario_id, compare_id))


@router.get("/{identifier}/costs")
def construction_costs(identifier: UUID, scenario_id: str, revision: int = Query(ge=1)):
    def read():
        plan = require_plan(identifier)
        if plan['revision'] != revision:
            raise store.Conflict('Plan changed. Reload before estimating costs.')
        scenario = engine.find(plan['scenarios'], scenario_id)
        result = costs.calculate(plan, scenario, CostSettings.model_validate(scenario.get('cost_settings', {})))
        return {**result, 'plan_id': str(identifier), 'scenario_id': scenario_id, 'revision': plan['revision']}
    return execute(read)


@router.get("/{identifier}/land-use")
def plan_land_use(identifier: UUID):
    plan = execute(lambda: require_plan(identifier))
    if not warehouse_configured():
        raise HTTPException(503, "Current parcel land use requires the PostGIS warehouse")
    try:
        return parcels.study_land_use(plan["study_area"])
    except (OSError, ValueError, DatabaseError):
        raise HTTPException(503, "Current parcel land use temporarily unavailable") from None


@router.post("/{identifier}/simulation/studies", status_code=201)
def simulation_study(identifier: UUID, body: SimulationInput):
    return save_simulation(identifier, body)


@router.post("/{identifier}/simulation/runs", status_code=202)
def simulation_run(identifier: UUID, body: SimulationRunInput):
    return save_simulation(identifier, body)


@router.post("/{identifier}/simulation/latest")
def latest_simulation(identifier: UUID, body: SimulationInput):
    from app.services.simulation.planning import store as simulations
    plan=execute(lambda: require_plan(identifier))
    if plan['revision'] != body.revision:
        raise HTTPException(409,'Plan changed. Reload before opening a saved run.')
    try:
        job=simulations.latest_zoning_job(f'zoning:{identifier}:{body.scenario_id}',
            f'Zoning plan {identifier}, revision {body.revision}, scenario {body.scenario_id}.',
            f'Scope {body.parcel_id or "study area"}.')
    except simulations.StoreError:
        raise HTTPException(503,'Simulation storage unavailable') from None
    return {'job':job, 'note':'Saved output uses its captured assumptions, not unsaved control changes.'}


def save_simulation(identifier, body):
    from app.services.simulation.planning import store as simulations
    from app.services.simulation.planning.context import canonical_input, preflight

    plan = execute(lambda: require_plan(identifier))
    if plan["revision"] != body.revision:
        raise HTTPException(409, "Plan changed. Reload before running simulation.")
    if body.parcel_id:
        parcel = execute(lambda: selected_site(plan, body.parcel_id, str(body.scenario_id)))
        plan.setdefault('parcels', {})[parcel['id']] = parcel
    study = execute(lambda: study_from_plan(plan, body))
    ready = execute(lambda: preflight(study))
    try:
        if isinstance(body, SimulationRunInput):
            saved, job = simulations.start_study(canonical_input(study), ready['context_hash'],
                f'zoning:{identifier}:{body.scenario_id}', body.mode, body.idempotency_key)
        else:
            saved = simulations.save_study(canonical_input(study), ready["context_hash"])
    except simulations.Conflict as error:
        raise HTTPException(409, str(error)) from None
    except simulations.StoreError:
        raise HTTPException(503, "Simulation storage unavailable") from None
    summary = {"id": saved["id"], "plan_id": str(identifier), "revision": plan["revision"],
            "scenario_id": str(body.scenario_id), "native_work_estimate": ready["native_work_estimate"],
            "model_version": ready["model_version"], "context_hash": ready["context_hash"]}
    return {'study': summary, 'job': job} if isinstance(body, SimulationRunInput) else summary
