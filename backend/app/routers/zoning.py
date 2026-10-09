from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from shapely.errors import GEOSException

from app.services.zoning import engine, store
from app.services.zoning.indicators import report
from app.services.zoning.models import Command, PlanInput

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


@router.post("/{identifier}/commands")
def change_plan(identifier: UUID, command: Command):
    def change():
        result = store.update(identifier, command.revision, lambda p: engine.apply(p, command))
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
        if command.action not in ("draw", "reshape"):
            raise ValueError("Preview supports draw and reshape operations")
        scenario = engine.editable(plan, command.scenario_id)
        zones, summary = engine.boundary_change(plan, scenario, command.payload, plan["revision"] + 1)
        return {"zones": zones, **summary}
    return execute(calculate)


@router.get("/{identifier}/indicators")
def indicators(identifier: UUID, scenario_id: str, compare_id: str | None = None):
    return execute(lambda: report(require_plan(identifier), scenario_id, compare_id))
