"""Regional screening. Native engines are not substituted by algebraic scores."""
from copy import deepcopy

from shapely.geometry import shape
from shapely.ops import transform, unary_union

from ..engine import polygon_and_area
from ..integrated import demand, geometry
from ..integrated.context import projection, digest
from .context import build_context, VERSION, state_keys
from .models import PlanningStudy, UtilityZone
from .utilities import aggregate
from . import services, spatial, comparison, baseline

METRICS = {"housing_units": "units", "residents": "people", "floor_area_m2": "m2",
           "green_m2": "m2", "impervious_m2": "m2", "freshwater_m3_day": "m3/day",
           "wastewater_m3_day": "m3/day", "energy_kwh_day": "kWh/day", "power_peak_kw": "kW",
           "person_trips_day": "person trips/day", "unretained_runoff_m3": "m3/event",
           "school_demand_students": "students", "school_served_students": "students",
           "school_unserved_students": "students", "school_mean_assigned_walk_m": "m/assigned student",
           "mean_shaded_receiver_m2": "m2", "mean_shaded_neighbour_m2": "m2"}


def metric_method(key):
    if key.startswith("school_"):
        return "School-age demand and shared capacity allocation by max-flow/min-cost on the declared walking graph; OSM topology in system demo, synthetic spine otherwise"
    if key.startswith("mean_shaded_"):
        return "Mean of polygon-union shadow area on fixed receivers over solar hours 8 through 17"
    if key == "power_peak_kw":
        return "Maximum of the sum of same-hour background and parcel power profiles; not a sum of independent peaks"
    if key == "unretained_runoff_m3":
        return "Rain depth times surface areas and runoff coefficients minus available storage, clipped at zero per parcel; not native flood prediction"
    if key in ("housing_units", "residents", "floor_area_m2", "green_m2", "impervious_m2"):
        return "Totals from deduplicated physical parcels in the scenario; residents include the declared regional background once"
    return "Versioned coefficient-library demand and operating profiles, summed once per parcel and declared utility zone"


def evaluate(study, context, active_project_ids):
    active = set(active_project_ids)
    parcel_results, parcels_seen = [], set()
    for project in sorted(study.projects, key=lambda p: (p.id not in active, p.id)):
        key = shape(project.site.model_dump()).normalize().wkb_hex
        if key in parcels_seen:
            continue  # Mutually exclusive designs on the same registered parcel.
        parcels_seen.add(key)
        design = project.development if project.id in active else project.baseline
        analysis = geometry.analyze(project.site, design)
        loads = demand.calculate(design, analysis["floor_areas"], context["library"])
        surfaces = analysis["metrics"]["surfaces_m2"]
        gross = context["library"]["rainfall_mm"]/1000*sum(area*context["library"]["runoff_coefficients"][kind] for kind, area in surfaces.items())
        runoff = max(0, gross-(design.storage_m3-design.storage_initial_m3))
        parcel_results.append({"id": project.id, "active": project.id in active,
                               "utility_zone_id": project.utility_zone_id, "catchment_id": project.catchment_id,
                               "baseline_occupancy": project.baseline_occupancy,
                               "geometry": analysis["metrics"], "demand": loads,
                               "unretained_runoff_m3": runoff, "housing_units": sum(b.units for b in design.buildings),
                               "source_kind": "user_design_on_synthetic_context" if project.id in active else project.baseline_kind})
    # Unknown baseline occupancy also contaminates the development delta when
    # an existing project is removed. Never label these placeholders measured.
    unknown = any(p.baseline_occupancy == "unknown" for p in study.projects)
    background = context["resolved_background"]
    zones = aggregate([UtilityZone(**z) for z in background["utility_zones"]], parcel_results, unknown_occupancy=unknown)
    total_power = [sum(z["hourly_power_kw"][h] for z in zones) for h in range(24)]
    metrics = {"housing_units": sum(p["housing_units"] for p in parcel_results),
               "residents": background["residents"]+sum(p["demand"]["residents"] for p in parcel_results),
               "floor_area_m2": sum(p["geometry"]["floor_area_m2"] for p in parcel_results),
               "green_m2": sum(p["geometry"]["surfaces_m2"]["green"] for p in parcel_results),
               "impervious_m2": sum(p["geometry"]["surfaces_m2"]["roof"]+p["geometry"]["surfaces_m2"]["paved"] for p in parcel_results),
               "freshwater_m3_day": sum(z["metrics"]["freshwater_m3_day"] for z in zones),
               "wastewater_m3_day": sum(z["metrics"]["wastewater_m3_day"] for z in zones),
               "energy_kwh_day": sum(total_power), "power_peak_kw": max(total_power),
               "person_trips_day": sum(p["demand"]["person_trips_day"] for p in parcel_results),
               "unretained_runoff_m3": sum(p["unretained_runoff_m3"] for p in parcel_results)}
    forward, _ = projection(shape(study.study_area.model_dump()))
    area = unary_union([transform(forward, shape(p.site.model_dump())) for p in study.projects]).area
    school = services.evaluate(study, parcel_results, background)
    metrics.update(school["metrics"])
    shadow = spatial.shadows(study, parcel_results, context.get("fixed_solar_context"))
    metrics.update(shadow["metrics"])
    output = {"active_project_ids": sorted(active), "metrics": metrics, "parcels": parcel_results,
            "baseline_ledger": baseline.ledger(study, context, parcel_results),
            "resolved_background": deepcopy(background),
            "school_services": school,
            "shadow": shadow,
            "utility_zones": zones, "hourly_power_kw": total_power,
            "registered_parcel_area_m2": area, "study_area_m2": polygon_and_area(study.study_area, maximum_area_m2=25_000_000)[1],
            "baseline_occupancy_unknown": unknown,
            "kind": "coefficient_screening_on_synthetic_context", "native_simulation": False,
            "unavailable_modules": ["traffic_SUMO", "drainage_SWMM", "healthcare_capacity_allocation", "park_capacity_allocation", "flood_depth_2D", "thermal_comfort"],
            "note": "Runoff sums screening parcel volumes, not peak network flow or node flooding. Geometry totals cover registered parcels only."}
    if study.planning_catalog == "qcvn_urban_2021":
        from .vietnam_rules import assess
        output["vietnam_planning_requirements"] = assess(study, output)
    return output


def compare(before, after, context_hash, context=None):
    rows = []
    for key, unit in METRICS.items():
        unknown = before["baseline_occupancy_unknown"] and key in ("residents", "freshwater_m3_day", "wastewater_m3_day", "energy_kwh_day", "power_peak_kw", "person_trips_day")
        if key.startswith("school_"):
            unknown = any(s["school_services"]["comparability"] == "insufficient_data" for s in (before, after))
        left, right = before["metrics"][key], after["metrics"][key]
        rows.append({"metric": key, "before": None if unknown else left, "after": None if unknown else right,
                     "delta": right-left if not unknown and left is not None and right is not None else None, "unit": unit,
                     "comparability": "insufficient_data" if unknown or left is None or right is None else "scenario_only",
                     "source_kind": context["source_kind"] if context else "synthetic", "context_hash": context_hash,
                     "method": metric_method(key),
                     "limitations": ["Scenario inputs and infrastructure are synthetic, not locally calibrated."]+(["Existing occupancy is unknown; numerical placeholders do not establish the true change."] if unknown else []),
                     "spatial_scope": "fixed_study_outdoor_receiver" if key.startswith("mean_shaded_") else "synthetic_school_service_graph" if key.startswith("school_") else "registered_parcels" if key in ("housing_units", "floor_area_m2", "green_m2", "impervious_m2", "unretained_runoff_m3", "person_trips_day") else "study_background_and_registered_parcels",
                     "time_window": "solar_date_hours_8_to_17_local" if key.startswith("mean_shaded_") else "daily_profile" if key.endswith("day") or key == "power_peak_kw" else "rain_event" if key == "unretained_runoff_m3" else "scenario_state"})
        if unknown:
            rows[-1].update(unavailable_reason="Unknown baseline occupancy or incomplete school demand/capacity; supplied scenario assumptions do not establish the actual impact.",
                            scenario_values={"before": left, "after": right,
                                             "delta": right-left if left is not None and right is not None else None,
                                             "basis": "Unverified numerical assumptions for scenario calculation only"})
        if context:
            module = "school" if key.startswith("school_") else "shadow" if key.startswith("mean_shaded_") else "drainage" if key == "unretained_runoff_m3" else "traffic" if key == "person_trips_day" else "utilities" if key in ("energy_kwh_day", "power_peak_kw", "freshwater_m3_day", "wastewater_m3_day") else "geometry"
            rows[-1].update(source_manifest_id=context["snapshot_manifest_id"], source_ids=list(context["data_coverage"]["modules"][module]["source_ids"]))
            if key == "residents":
                rows[-1]["source_ids"] = rows[-1]["source_ids"]+["regional_population"]
    return rows


def interaction_summary(combined_rows, standalone_rows):
    """Only publish interaction for metrics with compatible constituent deltas."""
    singles = [{row["metric"]: row for row in rows} for rows in standalone_rows]
    summary = {"metrics": {}, "comparability_by_metric": {}, "unavailable_reasons": {}, "scenario_values": {}}
    for combined in combined_rows:
        metric = combined["metric"]
        rows = [combined]+[single[metric] for single in singles]
        valid = all(row["comparability"] in ("comparable", "scenario_only") and row["delta"] is not None for row in rows)
        status = "scenario_only" if valid else "not_comparable" if any(row["comparability"] == "not_comparable" for row in rows) else "insufficient_data"
        summary["metrics"][metric] = combined["delta"]-sum(row["delta"] for row in rows[1:]) if valid else None
        summary["comparability_by_metric"][metric] = status
        if not valid:
            summary["unavailable_reasons"][metric] = "At least one constituent comparison is missing or incompatible; interaction is unavailable."
            deltas = [row.get("scenario_values", {}).get("delta", row["delta"]) for row in rows]
            summary["scenario_values"][metric] = {"value": deltas[0]-sum(deltas[1:]) if all(value is not None for value in deltas) else None,
                                                   "basis": "Unverified or invalid constituent results; not an established interaction"}
    return summary


def run_screening(study: PlanningStudy, progress=None):
    context = build_context(study)
    states = {}
    definitions = study.options+study.phases
    keys = state_keys(study)
    for index, key in enumerate(sorted(keys)):
        if progress:
            progress({"module": "screening", "active_project_ids": list(key), "done": index, "total": len(keys)})
        states[key] = evaluate(study, context, key)
    return assemble(study, context, states)


def assemble(study, context, states):
    """Present evaluated states without changing their physical context."""
    keys = set(states)
    baseline = states[()]
    def option_result(option):
        state = deepcopy(states[tuple(sorted(option.active_project_ids))])
        return {"id": option.id, "title": option.title, "state": state,
                "comparison": compare(baseline, state, context["sha256"], context)}
    options = [option_result(o) for o in sorted(study.options, key=lambda o: o.id)]
    phases = [option_result(p) for p in sorted(study.phases, key=lambda p: p.sequence)]
    previous, marginal = baseline, []
    for phase in phases:
        marginal.append({"phase_id": phase["id"], "compared_with": "baseline" if not marginal else phases[len(marginal)-1]["id"],
                         "rows": compare(previous, phase["state"], context["sha256"], context)})
        previous = phase["state"]
    feature_collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": p.id, "geometry": p.site.model_dump(mode="json"),
         "properties": {"project_id": p.id, "title": p.title, "source_kind": "user_selected_parcel",
                        "utility_zone_id": p.utility_zone_id, "context_hash": context["sha256"]}}
        for p in sorted(study.projects, key=lambda p: p.id)]}
    interactions = []
    for key in sorted(keys):
        if len(key) < 2 or not all((identifier,) in states for identifier in key):
            continue
        summary = interaction_summary(compare(baseline, states[key], context["sha256"], context),
                                      [compare(baseline, states[(p,)], context["sha256"], context) for p in key])
        interactions.append({"active_project_ids": list(key), "context_hash": context["sha256"],
                             "method": "Combined delta minus sum of standalone deltas; scenario interaction, not causal attribution.",
                             **summary})
    result = {"workflow": "planning_study", "model_version": VERSION, "mode": "screening",
            "inputs": context["inputs"], "input_sha256": digest(context["inputs"]), "context": context,
            "baseline": baseline, "options": options, "phases": phases, "marginal_effects": marginal,
            "interaction_effects": interactions,
            "standalone_states": {identifier: deepcopy(states[(identifier,)]) for identifier in sorted(p.id for p in study.projects) if (identifier,) in states},
            "unique_states_evaluated": len(states), "spatial_artifacts": {"parcels": feature_collection},
            "ranking": {"status": "not_requested", "note": "No automatic overall winner from unlike benefits/pressures."},
            "limitations": context["limitations"]+baseline["unavailable_modules"]}
    result["ranking"] = comparison.rank(study, result)
    from .normalization import attach
    attach(study, result)
    return result
