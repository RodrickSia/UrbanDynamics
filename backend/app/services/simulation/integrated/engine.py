from copy import deepcopy
from shapely.geometry import Point, mapping
from shapely.ops import transform

from . import demand, geometry, solvers
from .context import build_context, digest
from .models import Design, Conditions, IntegratedRequest

VERSION = "integrated-building-1.1"
UNAVAILABLE = {
    "thermal_comfort_SOLWEIG": "No radiation/DSM/material model; geometric shade available, no temperature delta",
    "flood_depth_2D": "No coupled surface hydraulics; SWMM node overflow available",
    "water_pressure_EPANET": "No pipe topology; demand and synthetic capacity screening only",
    "building_energy_EnergyPlus": "No envelope/HVAC thermal model; hourly load library only",
    "sanitary_network_hydraulics": "Sanitary demand available; stormwater network is separate",
    "legal_planning_check": "No applicable approved planning geometry/rules",
    "AI_explanation": "Deferred by user for this stage",
}
METRICS = {
    "building_density_percent": ("%", "context"), "far": ("m2/m2", "context"),
    "green_percent": ("%", "higher"), "canopy_m2": ("m2", "higher"),
    "impervious_percent": ("%", "lower"), "unretained_runoff_m3": ("m3/event", "lower"),
    "node_flooding_m3": ("m3/event (sample estimate)", "lower"),
    "traffic_delay_seconds": ("s/completed trip", "lower"), "traffic_queue_m": ("m", "lower"),
    "traffic_unfinished_vehicles": ("vehicles", "lower"), "traffic_undeparted_vehicles": ("vehicles", "lower"),
    "freshwater_m3_day": ("m3/day", "pressure"), "wastewater_m3_day": ("m3/day", "pressure"),
    "energy_kwh_day": ("kWh/day", "pressure"), "power_peak_kw": ("kW", "pressure"),
    "residents": ("people", "benefit"), "housing_units": ("units", "benefit"),
    "service_capacity": ("people/day", "benefit"), "service_unserved_people": ("people", "lower"),
    "mean_outdoor_shaded_percent": ("% daytime samples", "higher"), "neighbour_shadow_m2": ("m2 daytime mean", "context"),
    "road_length_m": ("m (scenario graph)", "context"),
}


def evaluate(site, raw_design, context):
    design = Design(**raw_design)
    geom = geometry.analyze(site, design)
    library = context["library"]
    loads = demand.calculate(design, geom["floor_areas"], library)
    solar = geometry.shadows(geom, design, Conditions(**context["conditions"]))
    traffic = solvers.traffic(design, loads, context)
    drainage = solvers.drainage(design, geom["metrics"]["surfaces_m2"], context)
    cx, cy = geom["metric_site"].centroid.coords[0]
    node_positions = {"S1": (cx, cy), "J1": (cx+50, cy), "O1": (cx+250, cy)}
    drainage["map"] = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": mapping(transform(geom["backward"], Point(node_positions[node["id"]]))),
         "properties": {**node, "kind": "synthetic", "feature": "swmm_node"}} for node in drainage["nodes"]]}
    runoff = library["rainfall_mm"]/1000*sum(area*library["runoff_coefficients"][key]
                                                   for key, area in geom["metrics"]["surfaces_m2"].items())
    available = design.storage_m3-design.storage_initial_m3
    service_demand = context["library"]["existing_service_users"]+loads["residents"]*.25
    service_available = context["library"]["service_capacity_people"]+loads["service_capacity"]
    service_unserved = max(0, service_demand-service_available)
    metrics = {**{k: v for k, v in geom["metrics"].items() if k in METRICS},
               **{k: v for k, v in loads.items() if k in METRICS},
               "housing_units": sum(b.units for b in design.buildings),
               "unretained_runoff_m3": max(0, runoff-available), "node_flooding_m3": drainage["node_flooding_m3"],
               "traffic_delay_seconds": traffic["mean_completed_delay_seconds"], "traffic_queue_m": traffic["max_queue_length_m"],
               "traffic_unfinished_vehicles": traffic["unfinished_vehicles"], "traffic_undeparted_vehicles": traffic["undeparted_vehicles"],
               "service_unserved_people": service_unserved,
               "mean_outdoor_shaded_percent": solar["mean_outdoor_shaded_percent"],
               "neighbour_shadow_m2": sum(x["neighbour_shadow_m2"] for x in solar["hourly"])/len(solar["hourly"]),
               "road_length_m": 600+design.added_road_m-design.removed_road_m}
    services = {"kind": "synthetic", "demand_people": service_demand, "capacity_people": service_available,
                "unserved_people": service_unserved, "walk_minutes_to_nearest": min(
                    f["properties"]["network_distance_m"] for f in context["services"])/80,
                "map": {"type": "FeatureCollection", "features": context["services"]},
                "method": "Distance along connected synthetic graph at 80 m/min; 0.25 service demand/resident. Not real accessibility coverage; no SUMO travel-time feedback."}
    road_length = metrics['road_length_m']
    if road_length < 0:
        raise ValueError('Removed road length exceeds the synthetic network plus added road length')
    road_region_area = geom['metric_site'].buffer(1000).area
    roads = {'kind': 'synthetic', 'region': '1 km buffer of site', 'region_area_m2': road_region_area,
             'length_m': road_length, 'density_km_per_km2': road_length*1000/road_region_area,
             'baseline_connected_components': 1, 'baseline_nodes': 4, 'baseline_undirected_edges': 3,
             'topology_change_simulated': False, 'design_added_m': design.added_road_m, 'design_removed_m': design.removed_road_m,
             'method': 'Length screening in stated region; connectivity is the frozen synthetic graph, not a real OSM network'}
    return {"design_sha256": digest(raw_design), "metrics": metrics, "gis": geom["metrics"], "demand": loads,
            "runoff": {"engine": "coefficient-screening-1", "kind": "synthetic", "gross_m3": runoff,
                       "empty_storage_m3": available, "retained_potential_m3": min(runoff, available),
                       "unretained_m3": max(0, runoff-available),
                       "limitations": "Screening with empty storage, no within-event outlet discharge; independent of SWMM results"},
            "traffic": traffic, "drainage": drainage, "shadow": solar, "services": services, "roads": roads,
            "buildings_map": {"type": "FeatureCollection", "features": [
                {"type": "Feature", "geometry": b.footprint.model_dump(), "properties": {
                    "name": b.name, "use": b.use, "height_m": b.height_m, "kind": "design"}} for b in design.buildings]},
            "validity": {"swmm_balance_passed": drainage["balance_passed"], "traffic_count_balanced":
                traffic["planned_vehicles"] == traffic["completed_vehicles"]+traffic["unfinished_vehicles"]+traffic["undeparted_vehicles"]}}


def assess(before, after, context):
    rows = []
    for metric, (unit, direction) in METRICS.items():
        b, a = before["metrics"][metric], after["metrics"][metric]
        delta = a-b
        if abs(delta) < max(1e-5, abs(b)*.001):
            verdict = "unchanged"
        elif direction == "context":
            verdict = "context_change"
        elif direction == "pressure":
            verdict = "increased_demand" if delta > 0 else "reduced_demand"
        else:
            better = delta > 0 if direction in ("higher", "benefit") else delta < 0
            verdict = ("benefit" if direction == "benefit" else "better") if better else "worse"
        rows.append({"metric": metric, "unit": unit, "baseline": b, "development": a, "delta": delta,
                     "role": direction, "verdict": verdict, "kind": "estimated_on_synthetic_context"})
    lib = context["library"]
    goals = lib["goals"]
    checks = [
        ("node_flooding_m3", after["metrics"]["node_flooding_m3"] <= before["metrics"]["node_flooding_m3"]*1.1+1e-6,
         before["metrics"]["node_flooding_m3"]*1.1),
        ("traffic_incomplete_vehicles", after["metrics"]["traffic_unfinished_vehicles"]+after["metrics"]["traffic_undeparted_vehicles"] == 0, 0),
        ("green_percent", after["metrics"]["green_percent"] >= goals["green_min_percent"]-.001, goals["green_min_percent"]),
        ("impervious_percent", after["metrics"]["impervious_percent"] <= goals["impervious_max_percent"]+.001, goals["impervious_max_percent"]),
        ("unretained_runoff_m3", after["metrics"]["unretained_runoff_m3"] <= before["metrics"]["unretained_runoff_m3"]*(1+goals["runoff_increase_max_percent"]/100),
         before["metrics"]["unretained_runoff_m3"]*(1+goals["runoff_increase_max_percent"]/100)),
    ]
    for metric, key in (("freshwater_m3_day", "water_spare_m3_day"), ("wastewater_m3_day", "wastewater_spare_m3_day")):
        limit = before["metrics"][metric]+lib[key]
        checks.append((metric, after["metrics"][metric] <= limit, limit))
    additional_power_peak = max(a-b for a, b in zip(after['demand']['hourly']['power_kw'], before['demand']['hourly']['power_kw']))
    checks.append(('power_peak_kw', additional_power_peak <= lib['power_spare_kw'], lib['power_spare_kw']))
    benefits = [x["metric"] for x in rows if x["verdict"] in ("benefit", "better")]
    pressures = [x["metric"] for x in rows if x["verdict"] in ("worse", "increased_demand")]
    return {"rows": rows, "benefits": benefits, "pressures": pressures,
            "verdict": "mixed" if benefits and pressures else "benefits" if benefits else "pressures" if pressures else "unchanged",
            "targets": [{"metric": m, "met": bool(ok), "limit": limit, "kind": "synthetic_project_goal",
                         "tolerance": .001 if m in ('green_percent', 'impervious_percent') else 0,
                         **({"comparison_basis": "max additional simultaneous hourly kW", "comparison_value": additional_power_peak}
                            if m == 'power_peak_kw' else {})} for m, ok, limit in checks],
            "targets_met": all(ok for _, ok, _ in checks),
            "invalid_engines": [f"{state}:{name}" for state, values in (("baseline", before), ("development", after))
                                for name, valid in values["validity"].items() if not valid],
            "note": "Added housing/service benefits and infrastructure pressures are separate; no overall planning approval or weighted winner score."}


def predict(request: IntegratedRequest):
    context = build_context(request)
    inputs = request.model_dump(mode="json")
    development = inputs["development"]
    # Validate both designs before launching expensive processes.
    geometry.analyze(request.site, Design(**context["baseline"]))
    geometry.analyze(request.site, request.development)
    before = evaluate(request.site, context["baseline"], context)
    after = evaluate(request.site, development, context)
    return {"workflow": "integrated_building_impact", "model_version": VERSION, "inputs": inputs,
            "input_sha256": digest({"inputs": inputs, "context_sha256": context["sha256"], "version": VERSION}),
            "context": context, "variants": {"baseline": before, "development": after},
            "assessment": assess(before, after, context), "recommendations": [], "recommendation_status": "not_requested",
            "unavailable_modules": UNAVAILABLE,
            "warnings": ["Synthetic scenario outputs have not been calibrated/validated against local observations.",
                         "Low/base/high are stress cases, not statistical confidence intervals.",
                         "Added/removed road lengths are design screening only; SUMO graph remains frozen.",
                         "Daily visitors are people visits, not additional permanent population."]}


def dominates(a, b):
    objectives = ("unretained_runoff_m3", "node_flooding_m3", "freshwater_m3_day", "wastewater_m3_day",
                  "energy_kwh_day", "power_peak_kw", "traffic_delay_seconds", "traffic_queue_m",
                  "traffic_unfinished_vehicles", "traffic_undeparted_vehicles", "service_unserved_people")
    benefits = ("green_percent", "canopy_m2", "mean_outdoor_shaded_percent")
    av = [a["predicted"]["metrics"][k] for k in objectives]+[-a["predicted"]["metrics"][k] for k in benefits]+[a["estimated_cost_vnd"]]
    bv = [b["predicted"]["metrics"][k] for k in objectives]+[-b["predicted"]["metrics"][k] for k in benefits]+[b["estimated_cost_vnd"]]
    return all(x <= y+1e-6 for x, y in zip(av, bv)) and any(x < y-1e-6 for x, y in zip(av, bv))


def recommend(source, constraints):
    result = deepcopy(source)
    result.pop("id", None)
    result.pop("created_at", None)
    result["parent_id"] = source["id"]
    result["recommendation_constraints"] = constraints.model_dump(mode="json")
    original = Design(**source["inputs"]["development"])
    context = source["context"]
    before = source["variants"]["baseline"]
    development = source["variants"]["development"]
    costs = context["library"]["costs_vnd"]
    candidates = []
    seen_designs = set()
    for label in ("landscape_drainage", "operations_utilities", "combined"):
        design = original.model_copy(deep=True)
        actions, cost = [], 0.0
        if original.paved_m2 < constraints.minimum_paved_m2:
            continue
        if label != "operations_utilities":
            if constraints.allow_surface_changes:
                converted = min(constraints.maximum_surface_conversion_m2, max(0, original.paved_m2-constraints.minimum_paved_m2))
                if converted:
                    design.paved_m2 -= converted
                    design.green_m2 += converted/2
                    design.permeable_m2 += converted/2
                    cost += converted/2*(costs["green_m2"]+costs["permeable_m2"])
                    actions.append({"action": "convert_paved_to_green_and_permeable", "m2": converted})
            if constraints.allow_storage and constraints.maximum_additional_storage_m3:
                addition = min(constraints.maximum_additional_storage_m3, 10000-original.storage_m3)
                design.storage_m3 += addition
                cost += addition*costs["storage_m3"]
                actions.append({"action": "add_detention_tank", "m3": addition, "outlet_diameter_m": design.storage_outlet_diameter_m,
                                "basis": "Synthetic orifice/storage; hydraulic feasibility not surveyed"})
        if label != "landscape_drainage" and constraints.allow_operations:
            if not original.efficient_fixtures:
                design.efficient_fixtures = True
                people = sum(b.residents+b.staff+b.daily_visitors+b.daily_users for b in original.buildings)
                cost += people*costs["fixtures_person"]
                actions.append({"action": "efficient_fixtures", "effect_basis": "Synthetic fixture demand multiplier 0.75; verify product/design"})
            if not original.efficient_equipment:
                design.efficient_equipment = True
                cost += development["gis"]["floor_area_m2"]*costs["equipment_m2"]
                actions.append({"action": "efficient_electrical_equipment", "effect_basis": "Synthetic equipment load multiplier 0.8; not EnergyPlus HVAC prediction"})
            if original.stagger_hours < 3:
                design.stagger_hours = min(3, original.stagger_hours+1)
                cost += costs["schedule"]
                actions.append({"action": "stagger_shared_activity_schedule", "hours": design.stagger_hours,
                                "feasibility": "Operational assumption requires resident/staff agreement; preserves daily trips/demand"})
            if original.ev_chargers and original.ev_charging_hour != 1:
                design.ev_charging_hour = 1
                actions.append({"action": "shift_EV_charging", "hour_local": 1})
        if not actions or (constraints.budget_vnd is not None and cost > constraints.budget_vnd):
            continue
        design_hash = digest(design.model_dump(mode='json'))
        if design_hash in seen_designs:
            continue
        seen_designs.add(design_hash)
        predicted = evaluate(IntegratedRequest(**source["inputs"]).site, design.model_dump(mode="json"), context)
        assessment = assess(before, predicted, context)
        tradeoff = assess(development, predicted, context)
        if not any(row["verdict"] in ("better", "reduced_demand") for row in tradeoff["rows"]):
            continue
        candidates.append({"name": label, "actions": actions, "design": design.model_dump(mode="json"),
                           "estimated_cost_vnd": cost, "cost_kind": "synthetic", "budget_applied": constraints.budget_vnd is not None,
                           "predicted": predicted, "assessment": assessment, "versus_proposal": tradeoff,
                           "scale_preserved": design.buildings == original.buildings})
    for candidate in candidates:
        candidate["pareto"] = not any(dominates(other, candidate) for other in candidates if other is not candidate)
    candidates.sort(key=lambda c: (bool(c["assessment"]["invalid_engines"]),
                                  -sum(x["met"] for x in c["assessment"]["targets"]), c["estimated_cost_vnd"]))
    result["recommendations"] = candidates
    result["search_scope"] = "Three explicit action templates; no claim of exhaustive design optimization. Pareto relative to these candidates only."
    result["recommendation_status"] = "targets_met" if any(c["assessment"]["targets_met"] and not c["assessment"]["invalid_engines"] for c in candidates) else "partial" if candidates else "no_feasible_candidate"
    result["input_sha256"] = digest({"parent_sha256": source["input_sha256"], "constraints": result["recommendation_constraints"], "version": VERSION})
    return result
