"""One-at-a-time demand sensitivity on a saved, immutable background context."""
from copy import deepcopy
import math

from . import demand, geometry, solvers
from .context import digest
from .engine import assess, utility_checks
from .models import Design, IntegratedRequest
from .parameter_catalog import catalog, set_value

VERSION = "demand-sensitivity-1"
DEMAND_METRICS = {
    "freshwater_m3_day": "m3/day", "wastewater_m3_day": "m3/day", "energy_kwh_day": "kWh/day",
    "power_peak_kw": "kW", "person_trips_day": "person trips/day", "car_trips_day": "car trips/day",
    "motorcycle_trips_day": "motorcycle trips/day", "vehicle_peak_hour": "vehicle trips/hour"}
TRAFFIC_METRICS = {
    "traffic_delay_seconds": "s/completed trip", "traffic_queue_m": "m",
    "traffic_unfinished_vehicles": "vehicles", "traffic_undeparted_vehicles": "vehicles"}


def delta_verdict(before, after):
    delta = after-before
    if abs(delta) < max(1e-5, abs(before)*.001):
        return "unchanged"
    return "increased_demand" if delta > 0 else "reduced_demand"


def rows_for(loads):
    return [{"metric": metric, "unit": unit, "baseline": loads["baseline"][metric],
             "development": loads["development"][metric],
             "delta": loads["development"][metric]-loads["baseline"][metric],
             "verdict": delta_verdict(loads["baseline"][metric], loads["development"][metric])}
            for metric, unit in DEMAND_METRICS.items()]


def analyze_source(source, request):
    frozen = source["context"]
    integrity = "verified"
    if digest({k: v for k, v in frozen.items() if k not in ("sha256", "created_at")}) != frozen["sha256"]:
        # Older synthetic SUMO runs wrote edge statistics into context.roads.
        # Recover only that known mutation if the original input hash matches.
        restored = deepcopy(frozen)
        if source["model_version"] in ("integrated-building-1.1", "integrated-building-1.2", "integrated-building-1.3") and frozen.get("traffic_network_kind") == "synthetic":
            for feature in restored["roads"]:
                feature["properties"].pop("simulated", None)
        if digest({k: v for k, v in restored.items() if k not in ("sha256", "created_at")}) != frozen["sha256"]:
            raise ValueError("Stored simulation context integrity check failed")
        frozen = restored
        integrity = "legacy_road_output_mutation_recovered_without_changing_parent"
    parsed = IntegratedRequest(**source["inputs"])
    designs = {"baseline": Design(**frozen["baseline"]), "development": parsed.development}
    areas = {key: geometry.analyze(parsed.site, design)["floor_areas"] for key, design in designs.items()}
    info = deepcopy(frozen.get("demand_parameter_catalog") or catalog(frozen["library"]))
    records = info["parameters"]
    uses = {block.use for design in designs.values() for block in design.buildings}
    allowed = {key: r for key, r in records.items()
               if r["group"] != "traffic_background" and (not r.get("use") or r["use"] in uses)}
    if request.mode == "native_traffic":
        allowed = {key: r for key, r in records.items() if r["group"] in ("traffic", "traffic_background")
                   and (not r.get("use") or r["use"] in uses)}
    parameter_ids = request.parameter_ids or sorted(allowed)
    if not parameter_ids or any(key not in allowed for key in parameter_ids):
        raise ValueError("Sensitivity parameter is unsupported, not applicable to this run, or incompatible with the selected mode")

    def calculation(context, native=False):
        loads = {key: demand.calculate(design, areas[key], context["library"]) for key, design in designs.items()}
        rows = rows_for(loads)
        utility, peak = utility_checks(loads["baseline"], loads["development"], context["library"])
        targets = [{"metric": key, "met": bool(ok), "limit": limit, "kind": "synthetic_capacity_screening",
                    "comparison_value": peak if key == "power_peak_kw" else loads["development"][key]}
                   for key, ok, limit in utility]
        result = {"rows": rows, "targets": targets, "hourly": {key: load["hourly"] for key, load in loads.items()}}
        if native:
            # Only traffic depends on these selected coefficients. Keep the
            # original hydraulic/shadow results and recompute actual SUMO runs.
            variants = deepcopy(source["variants"])
            for key, design in designs.items():
                variant = variants[key]
                traffic = solvers.traffic(design, loads[key], context)
                variant["traffic"] = traffic
                variant["demand"] = loads[key]
                for metric in ("freshwater_m3_day", "wastewater_m3_day", "energy_kwh_day", "power_peak_kw"):
                    variant["metrics"][metric] = loads[key][metric]
                for metric, field in (("traffic_delay_seconds", "mean_completed_delay_seconds"),
                                      ("traffic_queue_m", "max_queue_length_m"),
                                      ("traffic_unfinished_vehicles", "unfinished_vehicles"),
                                      ("traffic_undeparted_vehicles", "undeparted_vehicles")):
                    variant["metrics"][metric] = traffic[field]
                variant["validity"]["traffic_count_balanced"] = traffic["planned_vehicles"] == traffic["completed_vehicles"]+traffic["unfinished_vehicles"]+traffic["undeparted_vehicles"]
                traffic["completed_fraction"] = traffic["completed_vehicles"]/max(1, traffic["planned_vehicles"])
                traffic["delay_comparability"] = "completed_trips_only_with_incomplete_population" if traffic["unfinished_vehicles"]+traffic["undeparted_vehicles"] else "all_planned_trips_completed"
            assessment = assess(variants["baseline"], variants["development"], context)
            result["rows"].extend(row for row in assessment["rows"] if row["metric"] in TRAFFIC_METRICS)
            result["targets"].extend(t for t in assessment["targets"] if t["metric"] == "traffic_incomplete_vehicles")
            result["variants"] = variants
            result["native_validity"] = {key: variant["validity"] for key, variant in variants.items()}
        return result

    # Native reference results are already in the saved run. Baseline/development
    # have the same seed, comparison hour and frozen library as the OAT cases.
    reference = calculation(frozen)
    if request.mode == "native_traffic":
        reference["rows"].extend(row for row in source["assessment"]["rows"] if row["metric"] in TRAFFIC_METRICS)
        reference["targets"].extend(t for t in source["assessment"]["targets"] if t["metric"] == "traffic_incomplete_vehicles")
    cases, parameter_specs = [], []
    for key in parameter_ids:
        record = records[key]
        original = record["value"]
        minimum, maximum = record["hard_bounds"]
        if key in ("car_person_share", "motorcycle_person_share"):
            other = "motorcycle_person_share" if key == "car_person_share" else "car_person_share"
            maximum = min(maximum, 1-frozen["library"][other])
        bounds = []
        for label, multiplier in (("low", request.low_multiplier), ("high", request.high_multiplier)):
            proposed = original*multiplier
            value = min(maximum, max(minimum, proposed))
            if key in ("ev_hours", "background_vehicles_hour"):
                value = max(math.ceil(minimum), min(math.floor(maximum), int(math.floor(value+.5))))
            changed = deepcopy(frozen)
            set_value(changed["library"], key, value)
            changed["library"]["parameter_provenance"][key] = {
                "kind": "synthetic", "value": value, "unit": record["unit"], "numeric_source": None,
                "value_status": "sensitivity_scenario_override", "base_parameter": deepcopy(record),
                "range_basis": "User-selected multiplier around frozen default, bounded by physical/model limits"}
            # Refresh only the changed catalog record; do not load current sources,
            # snapshots or rates into the parent context.
            changed["demand_parameter_catalog"] = deepcopy(info)
            changed["demand_parameter_catalog"]["parameters"][key] = {
                **deepcopy(record), "value": value, "kind": "synthetic", "numeric_source": None,
                "value_status": "sensitivity_scenario_override"}
            changed["sha256"] = digest({k: v for k, v in changed.items() if k not in ("created_at", "sha256")})
            output = calculation(changed, request.mode == "native_traffic")
            ref_rows = {r["metric"]: r for r in reference["rows"]}
            ref_targets = {t["metric"]: t for t in reference["targets"]}
            output.update(parameter_id=key, level=label, value=value, multiplier=multiplier,
                          value_was_bounded=abs(value-proposed) > 1e-12, unit=record["unit"],
                          context_sha256=changed["sha256"], provenance=changed["library"]["parameter_provenance"][key],
                          changed_verdicts=[r["metric"] for r in output["rows"] if r["verdict"] != ref_rows[r["metric"]]["verdict"]],
                          target_flips=[t["metric"] for t in output["targets"] if t["met"] != ref_targets[t["metric"]]["met"]])
            cases.append(output)
            bounds.append({"level": label, "value": value, "value_was_bounded": output["value_was_bounded"]})
        parameter_specs.append({"parameter_id": key, "unit": record["unit"], "reference": original, "tested_values": bounds,
                                "source_status": record["value_status"], "range_kind": "synthetic_multiplier_stress_test"})
    stability = []
    for ref in reference["rows"]:
        sampled = [next(r for r in case["rows"] if r["metric"] == ref["metric"]) for case in cases]
        verdicts = sorted({ref["verdict"], *(r["verdict"] for r in sampled)})
        stability.append({"metric": ref["metric"], "unit": ref["unit"], "reference_delta": ref["delta"],
                          "tested_delta_min": min([ref["delta"]]+[r["delta"] for r in sampled]),
                          "tested_delta_max": max([ref["delta"]]+[r["delta"] for r in sampled]),
                          "verdict_stable": len(verdicts) == 1, "tested_verdicts": verdicts})
    rankings = []
    ref_by_metric = {r["metric"]: r for r in reference["rows"]}
    for key in parameter_ids:
        low, high = (case for case in cases if case["parameter_id"] == key)
        high_by_metric = {r["metric"]: r for r in high["rows"]}
        changes = {r["metric"]: abs(high_by_metric[r["metric"]]["development"]-r["development"])/max(1, abs(ref_by_metric[r["metric"]]["development"]))
                   for r in low["rows"]}
        rankings.append({"parameter_id": key, "max_development_relative_span": max(changes.values()),
                         "metric_relative_spans": changes, "target_flip_count": len(low["target_flips"])+len(high["target_flips"])})
    rankings.sort(key=lambda r: (-r["target_flip_count"], -r["max_development_relative_span"], r["parameter_id"]))
    target_stability = [{"metric": ref["metric"], "reference_met": ref["met"],
                         "stable": all(next(t for t in case["targets"] if t["metric"] == ref["metric"])["met"] == ref["met"] for case in cases)}
                        for ref in reference["targets"]]
    report = {"version": VERSION, "mode": request.mode, "method": "one_at_a_time",
              "source_context_integrity": integrity,
              "reference_context_sha256": frozen["sha256"], "catalog": info, "reference": reference,
              "parameters": parameter_specs, "cases": cases, "stability": stability, "ranked_parameters": rankings,
              "target_stability": target_stability,
              "capacity_targets_stable": all(t["stable"] for t in target_stability if t["metric"] != "traffic_incomplete_vehicles"),
              "native_engines_recomputed": request.mode == "native_traffic",
              "not_recomputed": (["SWMM hydraulics", "shadow", "recommendations"] if request.mode == "native_traffic" else
                                 ["SUMO delay/queue/routes", "SWMM hydraulics", "shadow", "full multi-feature verdict and recommendations"]),
              "scope": "Demand and three utility capacity screens; native mode also recalculates traffic. Building plan, background population, weather, topology, seed, comparison hour and capacity limits are held fixed. Population-derived background is frozen unless background_vehicles_hour itself is varied.",
              "limitations": "Tested OAT envelope, not a confidence interval or joint worst case. Sensitivity does not calibrate rates or validate local infrastructure capacity. Ranking uses span / max(1, abs(reference development)); small metrics are scaled by one unit."}
    result = deepcopy(source)
    result.pop("id", None)
    result.pop("created_at", None)
    result["parent_id"] = source["id"]
    result["analysis_kind"] = "parameter_sensitivity"
    result["sensitivity_request"] = request.model_dump(mode="json")
    result["sensitivity"] = report
    result["input_sha256"] = digest({"parent_sha256": source["input_sha256"], "request": result["sensitivity_request"], "analysis_version": VERSION})
    return result
