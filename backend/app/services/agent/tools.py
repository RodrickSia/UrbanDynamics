import json
import os
from psycopg import Error as WarehouseError
from copy import deepcopy
from uuid import uuid4
from fastapi import HTTPException

from shapely.geometry import box, shape

from app.services.simulation.planning import system_demo, store as planning_store
from app.services.simulation.planning.context import preflight, canonical_input
from app.services.simulation.planning.models import PlanningStudy
from .models import Search, Program, Run, Verify

LAYER_IDS = {"population","parcels","planning","land-price","flood-history","flood-satellite","flood-risk","rain","public-buildings","traffic","green-space","road-density"}


def source(session):
    if not system_demo.enabled():
        raise ValueError("Installed snapshot integration is not enabled; select the bounded demo data source")
    if not session["snapshot_id"]:
        candidates = []
        for path in system_demo.directory().glob("*.json"):
            try:
                doc = system_demo.load(path.stem)
                candidates.append((doc.get("captured_at", ""), path.stem))
            except (ValueError, OSError, KeyError):
                continue
        if not candidates:
            raise ValueError("No source snapshot installed; cannot invent candidate parcels or baseline")
        session["snapshot_id"] = max(candidates)[1]
    doc = system_demo.load(session["snapshot_id"])
    return doc, {str(f["id"]): f for f in system_demo.candidates(doc)}


def summary(feature):
    properties = feature.get("properties", {})
    return {"parcel_id": str(feature["id"]), "area_m2": feature["demo_area_m2"],
            "attributes": {key: properties.get(key) for key in ("mdsdd","loai_dat_qh","phuong","quan","do_an","quyet_dinh")},
            "bbox": list(shape(feature["geometry"]).bounds), "vacancy": "not_established", "legal_approval": "not_established",
            "occupancy_and_capacity": "not_surveyed", "flood_safety": "not_established", "market_price": "not_established"}


def find_sites(session, args):
    body = Search(**args)
    doc, available = source(session)
    region = box(*body.bbox) if body.bbox else None
    matched = [f for f in available.values() if body.minimum_area_m2 <= f["demo_area_m2"] <= body.maximum_area_m2
               and (not body.land_use_codes or f.get("properties", {}).get("mdsdd") in body.land_use_codes)
               and (region is None or shape(f["geometry"]).intersects(region))]
    matched.sort(key=lambda f: (f["demo_area_m2"], str(f["id"])))
    selected = matched[:body.limit]
    session["candidate_features"] = [{"type":"Feature","id":str(f["id"]),"geometry":f["geometry"],
                                     "properties":{"parcel_id":str(f["id"]),"area_m2":f["demo_area_m2"]}} for f in selected]
    session["map_actions"].append({"type":"focus","bbox":body.bbox or doc["bbox"]})
    return {"snapshot_id": session["snapshot_id"], "captured_at": doc["captured_at"], "source_bbox": doc["bbox"],
            "matching_count": len(matched), "candidates": [summary(f) for f in selected], "ordering": "Ascending source geometry area, then ID; no risk/price/vacancy ranking",
            "limitations": ["This searches installed pilot parcels, not every plot in the city.","No footprint does not prove vacancy; absence of flood reports does not prove low risk.","Candidate qualification is restricted to the explicit area/land-use/bbox filters."]}


def inspect_parcels(session, args):
    ids = args.get("parcel_ids", [])
    if not ids or len(ids) > 6 or len(set(ids)) != len(ids):
        raise ValueError("Choose 1..6 unique parcel IDs")
    doc, available = source(session)
    if not set(ids) <= available.keys():
        raise ValueError("Parcel is outside the installed eligible source snapshot")
    session["selected_parcel_ids"] = ids
    old = {str(f["id"]):f for f in session["candidate_features"]}
    selected = [{"type":"Feature","id":key,"geometry":available[key]["geometry"],"properties":{"parcel_id":key,"area_m2":available[key]["demo_area_m2"]}} for key in ids]
    session["candidate_features"] = selected+[f for key,f in old.items() if key not in ids][:12]
    rows = [summary(available[key]) for key in ids]
    if os.getenv("AGENT_USE_WAREHOUSE", "0") == "1":
        from app.services import parcels
        for row in rows:
            try:
                detail = parcels.detail(int(row["parcel_id"]))
                row["current_public_detail"] = detail
            except (ValueError, OSError, RuntimeError, WarehouseError):
                row["current_public_detail"] = {"status":"unavailable"}
    return {"parcels": rows, "sources": doc.get("sources", {}), "captured_at":doc["captured_at"],
            "population": {"regional_bbox_prior":doc.get("population",{}).get("statistics",{}).get("population_sum"),"parcel_population":"unknown; regional total must not be assigned to one parcel"},
            "context_layers": {name: {"feature_count":len(layer.get("features",[])) if isinstance(layer,dict) else 0,"use":"context only; no calibration or legal determination"} for name,layer in doc.get("layers",{}).items()}}


def map_view(session, args):
    layers = args.get("layer_ids", [])
    if not set(layers) <= LAYER_IDS:
        raise ValueError("Unsupported map layer")
    bounds = args.get("bbox")
    Search(bbox=bounds)
    doc, _ = source(session)
    session["map_actions"].append({"type":"layers","layer_ids":layers})
    if bounds:
        session["map_actions"].append({"type":"focus","bbox":bounds})
    return {"map_action":"requested","layer_ids":layers,"source_bbox":doc["bbox"],
            "availability":"Frontend must use its data catalog/status; requesting a layer does not establish data availability"}


def read_context(session, args):
    from shapely.ops import transform, unary_union
    from app.services.simulation.integrated.context import projection
    name = args.get("layer")
    if name not in ("flood_history","flood_risk","flood_satellite","land_price","public_services"):
        raise ValueError("Unsupported source context layer")
    identifiers = args.get("parcel_ids",[])
    document, available = source(session)
    if not identifiers or len(identifiers)>6 or not set(identifiers)<=available.keys():
        raise ValueError("Context query needs eligible source parcel IDs")
    distance = float(args.get("buffer_m",250))
    limit = int(args.get("limit",6))
    if not 0<=distance<=1000 or not 1<=limit<=10:
        raise ValueError("Context query exceeds bounded radius/row limit")
    site = unary_union([shape(available[key]["geometry"]) for key in identifiers])
    forward,_ = projection(site)
    region = transform(forward,site).buffer(distance)
    if name == "public_services":
        from app.services.simulation.integrated.background import osm_features
        features = osm_features(document.get("osm",{}))[2]
    else:
        layer = document.get("layers",{}).get(name,{})
        features = layer.get("features",[]) if isinstance(layer,dict) else []
    found = []
    for feature in features:
        if feature.get("geometry") and transform(forward,shape(feature["geometry"])).intersects(region):
            found.append({"id":feature.get("id"),"properties":feature.get("properties",{})})
    return {"layer":name,"captured_at":document["captured_at"],"snapshot_id":session["snapshot_id"],
            "buffer_m":distance,"matching_count":len(found),"records":found[:limit],
            "status":"source_records_found" if found else "no_matching_records_in_installed_source",
            "limitations":"No matching observations is not evidence of no flooding, vacancy, legal permission or low price. Risk is rainfall-threshold context; satellite classification is not flood depth; road prices do not establish parcel frontage or compensation."}


def prepare_simulation(session, args):
    body = Program(**args)
    source(session)
    if body.use == "residential" and (body.housing_units is None or body.residents is None):
        raise ValueError("Ask for apartment units and residents; do not silently infer occupancy")
    if body.use != "residential" and body.staff is None and body.daily_users is None:
        raise ValueError("Ask for staff/daily users for this non-residential program")
    request = system_demo.Prepare(snapshot_id=session["snapshot_id"],parcel_ids=body.parcel_ids,
        parcel_groups=[body.parcel_ids] if body.grouped else [], mode=body.mode,
        housing_units=max(1,body.housing_units or 1), residents=max(1,body.residents or 1), floors=body.floors,
        floor_area_m2=body.floor_area_m2, background_mode=body.background_mode,
        planning_catalog="qcvn_urban_2021",traffic_network_mode="osm_snapshot",
        conditions={"traffic_hours":[18],"seeds":[2026,2027,2028]})
    inputs = system_demo.prepare(request)
    for project in inputs["projects"]:
        for building in project["development"]["buildings"]:
            building.update(use=body.use,units=body.housing_units or 0,residents=body.residents or 0,
                            staff=body.staff or 0,daily_users=body.daily_users or 0,service_capacity=body.service_capacity or 0)
    study = PlanningStudy(**inputs)
    ready = preflight(study)
    if len(session["drafts"]) >= 20:
        raise ValueError("Session draft limit reached; start a new bounded study session")
    identifier = str(uuid4())
    assumptions = ["Generated preliminary footprint fits declared floors/GFA; not an optimized design", "OSM accesses/signals/OD and drainage remain assumptions; source coverage is not calibration"]
    if body.background_mode == "synthetic_capacity_v1":
        assumptions.append("User-selected synthetic occupancy/capacity package; not measured conditions")
    session["drafts"][identifier] = {"inputs":canonical_input(study),"program":body.model_dump(mode="json"),"assumptions":assumptions,"preflight":ready}
    session["selected_parcel_ids"] = body.parcel_ids
    return {"draft_id":identifier,"program":body.model_dump(mode="json"),"assumptions":assumptions,
            "preflight":{"warnings":ready.get("warnings",[]),"native_work_estimate":ready.get("native_work_estimate"),"context_hash":ready["context_hash"]}}


def start_simulation(session, args, allow_native):
    body = Run(**args)
    draft_id = str(body.draft_id)
    draft = session["drafts"].get(draft_id)
    if draft is None:
        raise ValueError("Draft does not belong to this session")
    for identifier, previous in session["jobs"].items():
        if previous == {"draft_id":draft_id,"mode":body.mode}:
            return {"job_id":identifier,"status":planning_store.get_job(identifier)["status"],"reused":True}
    if len(session["jobs"]) >= 8:
        raise ValueError("Session solver-job budget reached")
    ready = preflight(PlanningStudy(**draft["inputs"]))
    if body.mode == "native":
        if not allow_native:
            raise ValueError("Native is not authorized in this UI request; ask user to enable native or run screening")
        work = ready["native_work_estimate"]
        if work["sumo_runs"] > int(os.getenv("AGENT_MAX_SUMO_RUNS", "24")):
            raise ValueError("Native workload exceeds agent pilot budget; reduce study scope")
    saved = planning_store.save_study(draft["inputs"], ready["context_hash"])
    task = planning_store.enqueue(saved["id"],body.mode,"agent-"+session["id"]+"-"+draft_id+"-"+body.mode)
    session["jobs"][task["id"]] = {"draft_id":draft_id,"mode":body.mode}
    return {"job_id":task["id"],"status":task["status"],"mode":body.mode,"result_available":False,
            "next":"Worker is asynchronous. Read results after completion; do not claim improvement yet."}


def compact_result(result):
    options = []
    for option in result.get("options",[]):
        rows = [{key: row.get(key) for key in ("metric","before","after","delta","unit","comparability","hour_local","seed")} for row in option["comparison"]+option.get("traffic_comparison",[])+option.get("drainage_comparison",[])]
        options.append({"id":option["id"],"title":option["title"],"comparisons":rows,
                        "utility_checks": [{"zone_id":zone["id"],"checks":zone["checks"]} for zone in option["state"]["utility_zones"]],
                        "school":option["state"]["school_services"]["metrics"],"school_limitations":option["state"]["school_services"]["limitations"],
                        "qcvn":option["state"].get("vietnam_planning_requirements")})
    return {"run_id":result["id"],"context_hash":result["context"]["sha256"],"source_note":result["inputs"]["source_note"],
            "options":options,"ranking":result.get("ranking"),"seed_analysis":result.get("seed_analysis"),
            "limitations":result.get("limitations",[]),"model_version":result["model_version"]}


def read_results(session, args):
    ids = args.get("job_ids", [])
    if not ids or len(ids) > 8 or not set(ids) <= session["jobs"].keys():
        raise ValueError("Read only solver jobs created by this agent session")
    rows = []
    for identifier in ids:
        task = planning_store.get_job(identifier)
        entry = {"job_id":identifier,"status":task["status"],"progress":task.get("progress"),"error":task.get("error")}
        if task["status"] == "succeeded":
            result = planning_store.load_document(task["result_id"],"run")
            entry["results"] = compact_result(result)
        rows.append(entry)
    pairs = []
    for variant_job in ids:
        metadata = session["jobs"][variant_job]
        variant = session["drafts"][metadata["draft_id"]]
        origin_id = variant.get("original_draft_id")
        if not origin_id:
            continue
        control = variant["changed_control"]
        original = session["drafts"][origin_id]
        left, right = deepcopy(original["inputs"]), deepcopy(variant["inputs"])
        for document in (left,right):
            for project in document["projects"]:
                project["development"].pop(control,None)
        for original_job in ids:
            previous = session["jobs"][original_job]
            if previous["draft_id"] == origin_id and previous["mode"] == metadata["mode"]:
                pairs.append({"original_job":original_job,"variant_job":variant_job,"changed_control":control,
                              "same_program":original["program"]==variant["program"],
                              "all_other_inputs_identical":left==right,
                              "basis":"Canonical inputs compared after excluding only the named design control; this includes background, rain, geometry and seeds. Different full context hashes are expected when a control changes."})
    return {"jobs":rows,"paired_input_audit":pairs,"comparison_basis":"Check same program, rain, background and seeds. Do not rank incomplete/different-basis studies or equate simulated baseline with observed conditions."}


def suggest_and_verify(session, args, allow_native):
    body = Verify(**args)
    if body.mode == "native" and not allow_native:
        raise ValueError("Native is not authorized in this UI request")
    if body.goal == "traffic" and body.mode != "native":
        raise ValueError("Traffic delay/queue improvement needs native comparison; screening cannot verify it")
    original = session["drafts"].get(str(body.draft_id))
    if original is None:
        raise ValueError("Draft does not belong to this session")
    if len(session["drafts"]) >= 20 or len(session["jobs"]) > 6:
        raise ValueError("Not enough session budget for paired verification")
    inputs = deepcopy(original["inputs"])
    for project in inputs["projects"]:
        design = project["development"]
        if body.goal == "water":
            design["efficient_fixtures"] = True
        elif body.goal == "power":
            design["efficient_equipment"] = True
        elif body.goal == "runoff":
            design["storage_m3"] = min(10000,max(design["storage_m3"],50))
        else:
            design["stagger_hours"] = max(design["stagger_hours"],2)
    study = PlanningStudy(**inputs)
    identifier = str(uuid4())
    controls = {"water":"efficient_fixtures","power":"efficient_equipment","runoff":"storage_m3","traffic":"stagger_hours"}
    session["drafts"][identifier] = {"inputs":canonical_input(study),"program":deepcopy(original["program"]),
                                   "original_draft_id":str(body.draft_id),"changed_control":controls[body.goal],
                                   "assumptions":original["assumptions"]+["Proposed scenario variant, not an installed improvement: "+body.goal],"preflight":preflight(study)}
    jobs = [start_simulation(session,{"draft_id":str(body.draft_id),"mode":body.mode},allow_native),
            start_simulation(session,{"draft_id":identifier,"mode":body.mode},allow_native)]
    return {"variant_draft_id":identifier,"goal":body.goal,"jobs":jobs,"program_preserved":True,
            "verification":"pending; improvement must be demonstrated by paired completed model results", "proposal":"One bounded existing design-control variant; not exhaustive optimization or an infrastructure upgrade."}


def execute(name, args, session, allow_native):
    from . import general_tools
    if name in general_tools.NAMES:
        try:
            return general_tools.execute(name,args,session,allow_native)
        except HTTPException as error:
            raise ValueError(str(error.detail)) from None
        except WarehouseError:
            raise ValueError('A required warehouse source is unavailable; no observation was invented') from None
    from . import development_tools
    if name in development_tools.NAMES:
        return development_tools.execute(name, args, session, allow_native)
    if name == "map_view":
        return map_view(session,args)
    if name == "find_sites":
        return find_sites(session,args)
    if name == "inspect_parcels":
        return inspect_parcels(session,args)
    if name == "read_context":
        return read_context(session,args)
    if name == "prepare_simulation":
        return prepare_simulation(session,args)
    if name == "start_simulation":
        return start_simulation(session,args,allow_native)
    if name == "read_results":
        return read_results(session,args)
    if name == "suggest_and_verify":
        return suggest_and_verify(session,args,allow_native)
    raise ValueError("Unknown agent tool")
