import csv
import io
import json
import hashlib
import os
import tempfile
from pathlib import Path
import zipfile
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from typing import Literal
from fastapi.responses import Response, FileResponse

from app.services.simulation.planning import store
from app.services.simulation.planning.context import preflight, canonical_input
from app.services.simulation.planning.models import PlanningStudy, RunRequest
from app.services.simulation.planning.presets import demo_study, rehousing_study, inclusive_rehousing_study, single_site_study
from app.services.simulation.planning.map_output import layer, LayerUnavailable
from app.services.simulation.planning.engine import METRICS

router = APIRouter(prefix="/api/v1/planning", tags=["planning-studies"])
preview_router = APIRouter(include_in_schema=False)


@preview_router.get("/simulation/planning")
def planning_page():
    return FileResponse(Path(__file__).resolve().parents[1]/"static"/"planning.html")


@preview_router.get("/simulation/planning.js")
def planning_script():
    return FileResponse(Path(__file__).resolve().parents[1]/"static"/"planning.js", media_type="text/javascript")


def required(identifier, kind):
    try:
        document = store.load_document(identifier, kind)
    except store.StoreError:
        raise HTTPException(503, "Planning storage unavailable") from None
    if document is None:
        raise HTTPException(404, f"Planning {kind} not found")
    return document


@router.get("/presets")
def presets():
    return {"single_site": single_site_study(), "site_selection": demo_study(), "cumulative": demo_study("cumulative"), "rehousing": rehousing_study(), "inclusive": inclusive_rehousing_study(),
            "capabilities": {"screening": True, "native": True, "uncertainty": True, "data_mode": "synthetic"}}


@router.post("/studies/preflight")
def prepare(body: PlanningStudy):
    try:
        return preflight(body)
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from None


def save_revision(body, parent_id=None):
    ready = prepare(body)
    try:
        return store.save_study(canonical_input(body), ready["context_hash"], parent_id)
    except store.StoreError:
        raise HTTPException(503, "Planning storage unavailable") from None


@router.post("/studies", status_code=201)
def create_study(body: PlanningStudy):
    return save_revision(body)


@router.post("/single-site/studies", status_code=201)
def create_single_site_study(body: PlanningStudy):
    """One building project, shared regional context and existing async jobs."""
    if len(body.projects) != 1:
        raise HTTPException(422, "Single-site study requires exactly one project")
    return save_revision(body)


@router.post("/studies/{identifier}/revisions", status_code=201)
def create_revision(identifier: UUID, body: PlanningStudy):
    required(identifier, "study")
    return save_revision(body, str(identifier))


@router.get("/studies/{identifier}")
def get_study(identifier: UUID):
    return required(identifier, "study")


@router.post("/studies/{identifier}/runs", status_code=202)
def create_job(identifier: UUID, body: RunRequest):
    document = required(identifier, "study")
    if body.mode == "uncertainty" and not document["inputs"].get("uncertainty"):
        raise HTTPException(422, "Declare study.uncertainty settings before requesting analysis")
    try:
        return store.enqueue(str(identifier), body.mode, body.idempotency_key)
    except store.Conflict as error:
        raise HTTPException(409, str(error)) from None
    except store.StoreError:
        raise HTTPException(503, "Planning storage unavailable") from None


@router.get("/jobs/{identifier}")
def get_job(identifier: UUID):
    try:
        job = store.get_job(identifier)
    except store.StoreError:
        raise HTTPException(503, "Planning storage unavailable") from None
    if job is None:
        raise HTTPException(404, "Planning job not found")
    return job


@router.post("/jobs/{identifier}/cancel")
def cancel_job(identifier: UUID):
    get_job(identifier)
    try:
        return store.cancel(identifier)
    except store.StoreError:
        raise HTTPException(503, "Planning storage unavailable") from None


@router.post("/jobs/{identifier}/retry", status_code=202)
def retry_job(identifier: UUID):
    get_job(identifier)
    try:
        return store.retry(identifier)
    except store.Conflict as error:
        raise HTTPException(409, str(error)) from None
    except store.StoreError:
        raise HTTPException(503, "Planning storage unavailable") from None


@router.get("/jobs/{identifier}/children")
def job_children(identifier: UUID):
    get_job(identifier)
    try:
        return {"job_id": str(identifier), "children": store.children(identifier), "note": "Complete child results are retained for retry; a partial job has no comparable full-study run."}
    except store.StoreError:
        raise HTTPException(503, "Planning storage unavailable") from None


@router.get("/jobs/{identifier}/children/{child_key}")
def job_child(identifier: UUID, child_key: str):
    body = job_children(identifier)
    child = next((c for c in body["children"] if c["child_key"] == child_key), None)
    if not child or child["status"] != "succeeded" or not child["result_id"]:
        raise HTTPException(404, "Completed job child not found")
    return required(child["result_id"], "child")
@router.get("/runs/{identifier}")
def get_run(identifier: UUID):
    return required(identifier, "run")


def case_document(document, case_id):
    if case_id is None:
        return document
    case = next((c for c in document.get("assumption_cases", []) if c["id"] == case_id), None)
    if case is None:
        raise HTTPException(422, "Unknown assumption case")
    return {**case["result"], "id": document["id"], "study_id": document["study_id"]}


@router.get("/runs/{identifier}/map")
def map_layer(identifier: UUID, option_id: str = "baseline",
              name: Literal["parcels", "school", "shadow", "roads", "drainage", "drainage_links"] = "parcels",
              hour: int = Query(default=7, ge=0, le=23), seed: int | None = Query(default=None, ge=0),
              interval: int = Query(default=0, ge=0), case_id: str | None = None,
              drainage_sample: int | None = Query(default=None, ge=0)):
    document = case_document(required(identifier, "run"), case_id)
    try:
        output = layer(document, option_id, name, hour, seed, interval, drainage_sample)
        output["assumption_case_id"] = case_id
        for feature in output["features"]:
            feature["properties"]["assumption_case_id"] = case_id
        return output
    except LayerUnavailable as error:
        raise HTTPException(409, str(error)) from None
    except KeyError as error:
        raise HTTPException(422, str(error)) from None


@router.get("/runs/{identifier}/timeseries")
def time_series(identifier: UUID, name: Literal["roads", "drainage", "drainage_links", "runoff"],
                object_id: str = Query(min_length=1, max_length=160), option_id: str = "baseline",
                offset: int = Query(default=0, ge=0), limit: int = Query(default=60, ge=1, le=300),
                hour: int = Query(default=7, ge=0, le=23), seed: int | None = Query(default=None, ge=0),
                catchment_id: str | None = None, case_id: str | None = None):
    from app.services.simulation.planning.series_output import series
    document = case_document(required(identifier, "run"), case_id)
    try:
        result = series(document, option_id, name, object_id, offset, limit, hour, seed, catchment_id)
        result["assumption_case_id"] = case_id
        return result
    except LayerUnavailable as error:
        raise HTTPException(409, str(error)) from None
    except KeyError as error:
        raise HTTPException(422, str(error)) from None


@router.get("/runs/{identifier}/artifacts")
def artifacts(identifier: UUID):
    document = required(identifier, "run")
    buffer, csv_stream = io.BytesIO(), io.StringIO(newline="")
    writer = csv.writer(csv_stream)
    writer.writerow(["case_id", "option_id", "metric", "before", "after", "delta", "unit", "comparability", "hour_local", "seed", "spatial_scope", "method", "time_window", "source_manifest_id", "source_ids", "limitations", "context_hash"])
    cases = document.get("assumption_cases", [{"id": "reference", "result": document}])
    for case in cases:
        for option in case["result"]["options"]+case["result"]["phases"]:
            for row in option["comparison"]+option.get("traffic_comparison", [])+option.get("drainage_comparison", []):
                writer.writerow([case["id"], option["id"]]+[row[key] for key in ("metric", "before", "after", "delta", "unit", "comparability")]+[row.get(key) for key in ("hour_local", "seed", "spatial_scope", "method")]+
                                [json.dumps(row.get("time_window"), ensure_ascii=False), row.get("source_manifest_id"), json.dumps(row.get("source_ids", [])), json.dumps(row.get("limitations", [])), row.get("context_hash")])
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("result.json", json.dumps(document, ensure_ascii=False, allow_nan=False))
        archive.writestr("study.json", json.dumps(document["inputs"], ensure_ascii=False, allow_nan=False))
        if "source_manifest" in document["context"]:
            archive.writestr("source-manifest.json", json.dumps(document["context"]["source_manifest"], ensure_ascii=False, allow_nan=False))
        if "analysis_request" in document:
            archive.writestr("analysis-request.json", json.dumps(document["analysis_request"], ensure_ascii=False, allow_nan=False))
            for case in document["assumption_cases"]:
                archive.writestr(f"cases/{case['id']}/input.json", json.dumps(case["result"]["inputs"], ensure_ascii=False, allow_nan=False))
                archive.writestr(f"cases/{case['id']}/result.json", json.dumps(case["result"], ensure_ascii=False, allow_nan=False))
                if "source_manifest" in case["result"]["context"]:
                    archive.writestr(f"cases/{case['id']}/source-manifest.json", json.dumps(case["result"]["context"]["source_manifest"], ensure_ascii=False, allow_nan=False))
        archive.writestr("parcels.geojson", json.dumps(document["spatial_artifacts"]["parcels"], ensure_ascii=False, allow_nan=False))
        archive.writestr("comparison.csv", csv_stream.getvalue().encode("utf-8-sig"))
        normalized_stream = io.StringIO(newline="")
        normalized_writer = csv.writer(normalized_stream)
        normalized_fields = ("metric", "normalization_basis", "numerator", "numerator_unit", "denominator", "denominator_unit", "value", "unit", "comparability", "unavailable_reason", "context_hash", "source_manifest_id")
        normalized_writer.writerow(["case_id", "option_id", *normalized_fields])
        programs = []
        for case in cases:
            for option in case["result"]["options"]+case["result"]["phases"]:
                if "declared_program" in option:
                    programs.append({"case_id": case["id"], "option_id": option["id"], "program": option["declared_program"]})
                for row in option.get("normalized_comparison", []):
                    normalized_writer.writerow([case["id"], option["id"], *[row.get(field) for field in normalized_fields]])
        if programs:
            archive.writestr("declared-programs.json", json.dumps(programs, ensure_ascii=False, allow_nan=False))
            archive.writestr("normalized-comparison.csv", normalized_stream.getvalue().encode("utf-8-sig"))
        ledger_stream = io.StringIO(newline="")
        ledger_writer = csv.writer(ledger_stream)
        ledger_writer.writerow(["case_id", "option_id", "physical_parcel_id", "project_id", "metric", "unit", "baseline", "accounting_removed", "replacement_added", "final", "delta", "certainty", "baseline_source_kind", "baseline_source"])
        has_ledger = False
        for case in cases:
            body = case["result"]
            states = [{"id": "baseline", "state": body["baseline"]}]+body["options"]+body["phases"]
            for option in states:
                for parcel in option["state"].get("baseline_ledger", {}).get("parcels", []):
                    has_ledger = True
                    for metric, values in parcel["loads"].items():
                        ledger_writer.writerow([case["id"], option["id"], parcel["physical_parcel_id"], parcel["project_id"], metric, METRICS[metric]]+
                                               [values[k] for k in ("baseline", "accounting_removed", "replacement_added", "final", "delta", "certainty")]+
                                               [parcel["baseline_source_kind"], parcel["baseline_source"]])
        if has_ledger:
            archive.writestr("baseline-ledger.csv", ledger_stream.getvalue().encode("utf-8-sig"))
        for option in [{"id": "baseline"}]+document["options"]+document["phases"]:
            for name in ("parcels", "school", "shadow", "drainage", "drainage_links", "roads"):
                try:
                    collection = layer(document, option["id"], name, hour=9 if name == "shadow" else document["inputs"]["conditions"]["traffic_hours"][0])
                except LayerUnavailable:
                    continue
                archive.writestr(f"maps/{option['id']}/{name}.geojson", json.dumps(collection, ensure_ascii=False, allow_nan=False))
        root = Path(os.getenv("SIMULATION_WORK_DIR", str(Path(tempfile.gettempdir())/"urban-dynamics-solvers"))).resolve()
        written = set()
        def include_manifests(value):
            if isinstance(value, list):
                for member in value:
                    include_manifests(member)
            elif isinstance(value, dict):
                if "artifact_id" in value and "files" in value:
                    directory = (root/value["artifact_id"]).resolve()
                    if directory.parent != root or not directory.is_dir():
                        raise HTTPException(410, "Planning solver artifacts unavailable")
                    for name, metadata in value["files"].items():
                        file = (directory/name).resolve()
                        if file.parent != directory or not file.is_file():
                            raise HTTPException(410, "Planning solver artifacts incomplete")
                        key = f"solvers/{directory.name}/{file.name}"
                        if key in written:
                            continue
                        raw = file.read_bytes()
                        if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                            raise HTTPException(409, "Planning solver artifact checksum mismatch")
                        archive.writestr(key, raw)
                        written.add(key)
                else:
                    for member in value.values():
                        include_manifests(member)
        include_manifests(document)
    return Response(buffer.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="planning-{identifier}.zip"'})
