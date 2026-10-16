import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field

from app.services.agent import service, store, tools
from app.services.agent.models import ChatRequest, Strict

router = APIRouter(prefix="/api/v1/agent",tags=["planning-agent"])


def access(x_agent_token: str | None = Header(default=None)):
    if os.getenv("AGENT_ENABLED","0") != "1":
        raise HTTPException(404,"Planning agent is disabled")
    expected = os.getenv("AGENT_ACCESS_TOKEN")
    if expected:
        import hmac
        if not x_agent_token or not hmac.compare_digest(expected,x_agent_token):
            raise HTTPException(401,"Agent preview token required")


@router.get("/config")
def configuration():
    return {"enabled":os.getenv("AGENT_ENABLED","0")=="1","model_configured":service.configured(),
            "model":os.getenv("OPENAI_MODEL","gpt-6-luna"),"requires_token":bool(os.getenv("AGENT_ACCESS_TOKEN")),
            "capabilities":["map_control","parcel_analysis","candidate_search","simulation","result_comparison","verified_design_variants",
                            "development_workspace","plan_scenarios","building_floor_editing","local_osm","live_sources","stale_result_audit",
                            "area_questions","named_places","multi_criteria_sites","planning_review","equal_program_site_studies","urban_evidence_reports",
                            "dataset_schema","structured_dataset_filters","spatial_dataset_joins","query_aggregation","query_refinement",
                            "postgis_query_pushdown","goong_v2_places","route_accessibility","route_display","explicit_scope"],
            "scope":"Urban map areas and multi-site studies without an open plan, plus current Development workspace; unavailable sources/capacity remain unknown"}


@router.post("/sessions",dependencies=[Depends(access)])
def create_session():
    return store.public(store.create())


@router.get("/sessions/{identifier}",dependencies=[Depends(access)])
def get_session(identifier: UUID):
    value = store.get(identifier)
    if value is None:
        raise HTTPException(404,"Agent session not found")
    return store.public(value)


@router.post("/chat",dependencies=[Depends(access)])
def chat(body: ChatRequest):
    try:
        return service.chat(body)
    except (ValueError,OSError) as error:
        raise HTTPException(422,str(error)) from None


class ToolRequest(Strict):
    arguments: dict[str,Any] = Field(default_factory=dict)
    snapshot_id: str | None = Field(default=None,pattern=r"^[a-f0-9]{64}$")
    allow_native: bool = False
    workspace: dict = Field(default_factory=dict)


@router.post("/sessions/{identifier}/tools/{name}",dependencies=[Depends(access)])
def manual_tool(identifier: UUID,name: str,body: ToolRequest):
    session = store.get(identifier)
    if session is None:
        raise HTTPException(404,"Agent session not found")
    if body.snapshot_id and body.snapshot_id != session["snapshot_id"]:
        if session["drafts"]:
            raise HTTPException(409,"Changing source requires a new session")
        session["snapshot_id"] = body.snapshot_id
    session["map_actions"] = []
    try:
        from app.services.agent.development_tools import bind_workspace
        bind_workspace(session, body.workspace)
        session["workspace_changed"] = False
        result = tools.execute(name,body.arguments,session,body.allow_native)
        store.save(session)
        return {**store.public(session),"tool_result":result}
    except (ValueError,KeyError,TypeError,OSError) as error:
        raise HTTPException(422,str(error)) from None
