"""Canonical study context. Collections with identity are order independent."""
from copy import deepcopy

from ..integrated.context import digest
from ..integrated.library import parameters
from .models import PlanningStudy

VERSION = "planning-studies-0.18"


def canonical_numbers(value):
    # JSON does not assign distinct semantics to 0 and 0.0. Pydantic reloads
    # default integer literals into declared float fields; hashes must survive it.
    if isinstance(value, dict):
        return {key: canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonical_input(study: PlanningStudy):
    document = study.model_dump(mode="json")
    document["normalization_bases"] = sorted(document["normalization_bases"])
    for collection in ("projects", "options", "utility_zones", "catchments", "school_facilities", "background_school_groups", "resident_transfers"):
        document[collection] = sorted(document[collection], key=lambda x: x["id"])
    document["phases"] = sorted(document["phases"], key=lambda x: x["sequence"])
    document["criteria"] = sorted(document["criteria"], key=lambda x: x["metric"])
    if document["uncertainty"]:
        document["uncertainty"]["cases"] = sorted(document["uncertainty"]["cases"], key=lambda x: x["id"])
        document["uncertainty"]["seeds"] = sorted(document["uncertainty"]["seeds"])
    for option in document["options"]+document["phases"]:
        option["active_project_ids"] = sorted(option["active_project_ids"])
    for transfer in document["resident_transfers"]:
        transfer["when_active_project_ids"] = sorted(transfer["when_active_project_ids"])
    document["conditions"]["traffic_hours"] = sorted(document["conditions"]["traffic_hours"])
    document["conditions"]["seeds"] = sorted(document["conditions"]["seeds"])
    if document["background_snapshot"]:
        document["background_snapshot"]["included_modules"] = sorted(document["background_snapshot"]["included_modules"])
        document["background_snapshot"]["parcels"] = sorted(document["background_snapshot"]["parcels"], key=lambda p: p["project_id"])
    return canonical_numbers(document)


def build_context(study: PlanningStudy):
    inputs = canonical_input(study)
    library = parameters(study.conditions.level, study.conditions.coefficient_profile)
    library["rainfall_mm"] = study.conditions.rainfall_mm
    from .background import resolve
    background = resolve(study)
    from .provenance import build
    manifest = build(study, inputs, library, VERSION, background)
    context = {"model_version": VERSION, "inputs": inputs, "library": library,
               "source_kind": "synthetic", "source_note": study.source_note,
               "source_manifest": manifest, "snapshot_manifest_id": manifest["id"],
               "resolved_background": background,
               "data_coverage": {"kind": "synthetic_fixture", "study_area": inputs["study_area"],
                                 "observed_camera_counts": False, "modules": manifest["coverage"]["modules"]},
               "comparison_hours": inputs["conditions"]["traffic_hours"],
               "seed_suite": inputs["conditions"]["seeds"],
               "limitations": ["All regional infrastructure, occupancy and background flows are scenario inputs, not observations.",
                               "School access uses a synthetic pedestrian spine; age fraction and places are assumptions, not enrollment forecasts. Healthcare/park capacity allocation is unavailable.",
                               "No legal planning approval, 2D flood depth, thermal comfort or power-flow inference."]}
    context = canonical_numbers(context)
    if study.data_mode == "demo_system":
        from .system_demo import attach_context
        context = attach_context(study, context)
        from .spatial import fixed_context
        context["fixed_solar_context"] = fixed_context(study)
        context["limitations"][1] = "School access uses OSM foot topology and estimated endpoint connectors; age fraction, capacity and enrollment remain unverified. Healthcare/park capacity allocation is unavailable."
    context["sha256"] = digest(context)
    return deepcopy(context)


def state_keys(study):
    keys = {tuple(sorted(option.active_project_ids)) for option in study.options+study.phases} | {()}
    if study.mode == "cumulative":
        keys.update((p.id,) for p in study.projects)
    return keys


def preflight(study: PlanningStudy):
    context = build_context(study)
    active_sets = state_keys(study)
    unknown = [p.id for p in study.projects if p.baseline_occupancy == "unknown"]
    uncertainty_estimate = None
    if study.uncertainty:
        # Validate every effective case now, before committing a lengthy job.
        from .uncertainty import effective_studies
        cases = effective_studies(study)
        uncertainty_estimate = {"cases": len(cases), "engine": study.uncertainty.engine,
                               "sumo_runs": len(active_sets)*len(study.conditions.traffic_hours)*len(study.uncertainty.seeds)*len(cases) if study.uncertainty.engine == "native" else 0,
                               "swmm_runs": len(active_sets)*len(study.catchments)*len(cases) if study.uncertainty.engine == "native" else 0}
    from .benchmark import estimate
    timing = {mode: estimate(study, context, mode) for mode in ("screening", "native")}
    if study.uncertainty:
        timing["uncertainty"] = estimate(study, context, "uncertainty")
    return {"model_version": VERSION, "context_hash": context["sha256"], "runtime_estimates": timing,
            "status": "ready", "source_kind": context["source_kind"], "context": context,
            "unique_states": len(active_sets),
            "native_work_estimate": {"sumo_runs": len(active_sets)*len(study.conditions.traffic_hours)*len(study.conditions.seeds),
                                     "swmm_runs": len(active_sets)*len(study.catchments)},
            "uncertainty_work_estimate": uncertainty_estimate,
            "baseline_unknown_occupancy_projects": unknown,
            "warnings": [f"{r['project_id']}: {flag}" for r in context.get("system_background",{}).get("planning_review",[]) for flag in r["flags"]]+(["Unknown baseline occupancy prevents firm capacity/demand comparisons."] if unknown else [])+
                         (["Generated traffic network extends beyond the study area; its explicit synthetic boundary is supplied in module coverage."] if not context["data_coverage"]["modules"]["traffic"]["inside_study_area"] else [])+
                         ["Infrastructure/OD capacities are synthetic and have not been locally calibrated."]}
