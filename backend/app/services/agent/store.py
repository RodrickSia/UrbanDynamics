import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from fastapi.encoders import jsonable_encoder


def connection():
    path = Path(os.getenv("AGENT_SQLITE_PATH", str(Path(os.getenv("PLANNING_SQLITE_PATH", ".runtime/studies.sqlite")).with_name("agent.sqlite"))))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.execute("CREATE TABLE IF NOT EXISTS agent_sessions (id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS agent_usage (day TEXT PRIMARY KEY,calls INTEGER NOT NULL)")
    db.commit()
    return db


def create():
    value = {"id": str(uuid4()), "snapshot_id": None, "selected_parcel_ids": [], "drafts": {}, "jobs": {}, "messages": [], "requests": {}, "map_actions": [], "candidate_features": []}
    save(value)
    return value


def get(identifier):
    with connection() as db:
        row = db.execute("SELECT payload FROM agent_sessions WHERE id=?", (str(identifier),)).fetchone()
    return json.loads(row[0]) if row else None


def save(value):
    with connection() as db:
        db.execute("INSERT INTO agent_sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (value["id"], json.dumps(jsonable_encoder(value), ensure_ascii=False,allow_nan=False)))


def reserve_call():
    day = datetime.now(timezone.utc).date().isoformat()
    limit = int(os.getenv("AGENT_DAILY_MODEL_CALL_LIMIT", "200"))
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT calls FROM agent_usage WHERE day=?", (day,)).fetchone()
        count = row[0] if row else 0
        if count >= limit:
            raise ValueError("Daily agent model-call budget reached")
        db.execute("INSERT INTO agent_usage VALUES (?,1) ON CONFLICT(day) DO UPDATE SET calls=calls+1", (day,))


def public(value):
    from shapely.geometry import shape
    first = next(iter(value['drafts'].values()),None)
    focus = list(shape(first['inputs']['study_area']).bounds) if first else None
    return {"session_id": value["id"], "snapshot_id": value["snapshot_id"], "selected_parcel_ids": value["selected_parcel_ids"],"focus_bbox":focus,
            "messages": value["messages"][-30:], "drafts": [{"id": key, "program": d["program"], "assumptions": d["assumptions"], "preflight": d["preflight"]} for key,d in value["drafts"].items()],
            "job_ids": list(value["jobs"]), "map_actions": value["map_actions"],
            "candidates": {"type": "FeatureCollection", "features": value["candidate_features"]},
            "workspace": value.get("workspace", {}), "workspace_changed": value.get("workspace_changed", False),
            "development_runs": {**value.get("development_runs", {}),**value.get("general_runs",{})}, "prepared_runs": value.get("prepared_runs", {}),
            "analysis_area":value.get('analysis_area'),
            "dataset_queries":value.get('dataset_queries',[]), "amenity_search":value.get('amenity_search'),
            "structured_queries":value.get('structured_queries',[]),
            "query_features":value.get('query_features'),
            "route_features":value.get('route_features'),"route_result":value.get('route_result'),
            "accessibility_results":list(value.get('accessibility_results',{}).values()),
            "last_search_ids":value.get('last_search_ids',[]),
            "assessments":[{k:a.get(k) for k in ('id','created_at','rows','criteria','common_scored_metrics','excluded_from_all_scores','ranking_status','method','unresolved')} for a in value.get('assessments',{}).values()],
            "area_reports":[{k:a.get(k) for k in ('id','title','population','roads','buildings','services','capacity','limits')} for a in value.get('area_reports',{}).values()],
            "general_studies":[{'id':k,'parcel_ids':a['parcel_ids'],'program':a['program']} for k,a in value.get('general_studies',{}).items()]}
