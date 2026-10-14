from fastapi import APIRouter, HTTPException

from app.routers.zoning import execute, require_plan
from app.services.area_indicators.engine import analyze
from app.services.area_indicators.models import AreaRequest

router = APIRouter(prefix='/api/v1/indicators', tags=['area indicators'])


@router.post('/area')
def area_indicators(body: AreaRequest):
    plan = execute(lambda: require_plan(body.plan_id)) if body.plan_id else None
    if plan and plan['revision'] != body.revision:
        raise HTTPException(409, 'Plan changed. Reload before calculating indicators.')
    return execute(lambda: analyze(body, plan))
