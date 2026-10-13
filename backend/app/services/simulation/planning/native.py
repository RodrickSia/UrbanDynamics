"""Evaluate alternatives and portfolios on common native solver networks."""
from copy import deepcopy

from ..integrated.solvers import workdir, manifest
from . import traffic, drainage, comparison
from .engine import run_screening, interaction_summary


def _pair_traffic(before, after, context_hash):
    left = {(r["hour_local"], r["seed"]): r for r in before["traffic"]["runs"]}
    output = []
    for result in after["traffic"]["runs"]:
        baseline = left[(result["hour_local"], result["seed"])]
        for key, unit in (("mean_completed_delay_seconds", "s/completed trip"), ("background_completed_delay_seconds", "s/completed background trip"), ("max_queue_length_m", "m"),
                          ("completed_vehicles", "vehicles"), ("unfinished_vehicles", "vehicles"), ("undeparted_vehicles", "vehicles")):
            b, a = baseline[key], result[key]
            comparable = b is not None and a is not None
            if key.endswith("delay_seconds") and (baseline["completed_fraction"] < 1 or result["completed_fraction"] < 1):
                comparable = False
            unknown = before["baseline_occupancy_unknown"]
            output.append({"metric": key, "before": None if unknown else b, "after": None if unknown else a, "delta": a-b if not unknown and a is not None and b is not None else None,
                           "unit": unit, "hour_local": result["hour_local"], "seed": result["seed"],
                           "context_hash": context_hash, "source_kind": result["source_kind"],
                           "spatial_scope": "shared_osm_public_network_and_assumed_accesses" if result["network_provenance"]["kind"] == "osm_topology_with_estimated_demand" else "shared_synthetic_corridor",
                           "method": "Paired SUMO runs on the same network/hour/seed; completed-trip delay, or queue samples every 30 seconds, or vehicle counts from trip/summary XML.",
                           "time_window": {"departures_seconds": [0, 3600], "simulation_seconds": [0, 4200], "hour_local": result["hour_local"]},
                           "limitations": result["limitations"]+(["Incomplete planned-trip population: completed-trip delay cannot establish a whole-network improvement."] if not comparable else []),
                           "comparability": "insufficient_data" if before["baseline_occupancy_unknown"] or not comparable else "scenario_only",
                           "comparability_reason": "unknown_baseline_occupancy" if before["baseline_occupancy_unknown"] else "incomplete_trip_bias" if not comparable else None})
            if unknown:
                output[-1]["scenario_values"] = {"before": b, "after": a, "delta": a-b if a is not None and b is not None else None,
                                                  "basis": "Unverified occupancy/OD assumptions; not an observed or established impact"}
    return output


def _pair_drainage(before, after, context_hash):
    return [{"metric": key, "before": before["metrics"][key], "after": after["metrics"][key],
             "delta": after["metrics"][key]-before["metrics"][key], "unit": unit, "source_kind": "synthetic",
             "spatial_scope": "declared_shared_catchments", "context_hash": context_hash,
             "method": "Sum of node overflow volumes integrated from 1-minute report samples" if key == "node_flooding_m3" else "Maximum of summed catchment runoff at matching 1-minute timestamps",
             "time_window": "Declared rain event plus 180-minute recession; report interval 60 seconds",
             "limitations": ["Synthetic shared drainage networks, not surveyed sewers; node overflow is not 2D flood depth."],
             "comparability": "scenario_only" if before["drainage"]["balance_passed"] and after["drainage"]["balance_passed"] else "not_comparable",
             "comparability_reason": None if before["drainage"]["balance_passed"] and after["drainage"]["balance_passed"] else "invalid_solver_balance"}
            for key, unit in (("node_flooding_m3", "m3/event (sample integration)"), ("runoff_peak_m3_s", "m3/s"))]


def prepare_network(study, context, checkpoint=None, child_executor=None):
    def child(kind, details, compute):
        return child_executor.run(context["sha256"], kind, details, compute) if child_executor else compute()
    def build_network():
        network_dir = workdir("planning-network")
        network = traffic.build_network(study, network_dir, checkpoint)
        network["artifacts"] = manifest(network_dir, "netconvert", child_executor.versions["sumo_package"] if child_executor else traffic.version("eclipse-sumo"))
        return network
    return child("network", {}, build_network)


def evaluate_native_state(study, context, state, network, checkpoint=None, child_executor=None):
    """Native physics shared by single-site and portfolio orchestration."""
    from .models import DrainageCatchment
    resolved_catchments = [DrainageCatchment(**c) for c in context["resolved_background"]["catchments"]]
    active = tuple(state["active_project_ids"])
    def child(kind, details, compute):
        return child_executor.run(context["sha256"], kind, details, compute) if child_executor else compute()
    runs = [child("SUMO", {"active_project_ids": list(active), "hour": hour, "seed": seed,
                           "network_hash": network["artifacts"]["files"]["network.xml"]["sha256"]},
                  lambda: traffic.run(study, state, network, hour, seed, checkpoint))
            for hour in sorted(study.conditions.traffic_hours) for seed in sorted(study.conditions.seeds)]
    drainage_runs = [child("SWMM", {"active_project_ids": list(active), "catchment_id": catchment.id},
                          lambda: drainage.run(study, state, context["library"], catchment, checkpoint))
                     for catchment in sorted(resolved_catchments, key=lambda c: c.id)]
    hydrograph = drainage.combine_runoff(drainage_runs)
    combined_runoff = hydrograph["runoff_m3_s"]
    state.update(native_simulation=True, kind="native_solver_on_mixed_context" if study.traffic_network_mode == "osm_snapshot" else "native_solver_on_synthetic_context",
                 traffic={"runs": runs, "count_balanced": all(r["count_balanced"] for r in runs)},
                 drainage={"catchments": drainage_runs, "balance_passed": all(r["balance_passed"] for r in drainage_runs),
                           "combined_runoff_m3_s": combined_runoff,
                           "combined_runoff_time_minutes": hydrograph["minute"],
                           "combined_runoff_peak_minute": hydrograph["peak_minute"],
                           "peak_method": "Maximum of sum of same-time samples; not sum of catchment peaks."})
    state["metrics"].update(node_flooding_m3=sum(r["node_flooding_m3"] for r in drainage_runs),
                             runoff_peak_m3_s=hydrograph["peak_m3_s"])
    state["unavailable_modules"] = [m for m in state["unavailable_modules"] if m not in ("traffic_SUMO", "drainage_SWMM")]
    return state


def run_native(study, checkpoint=None, child_executor=None):
    result = run_screening(study, checkpoint)
    context = result["context"]
    network = prepare_network(study, context, checkpoint, child_executor)
    states = {(): result["baseline"]}
    for option in result["options"]+result["phases"]:
        states.setdefault(tuple(option["state"]["active_project_ids"]), option["state"])
    for identifier, state in result["standalone_states"].items():
        states.setdefault((identifier,), state)
    for index, (active, state) in enumerate(sorted(states.items())):
        if checkpoint:
            checkpoint({"module": "native_state", "done": index, "total": len(states), "active_project_ids": list(active)})
        evaluate_native_state(study, context, state, network, checkpoint, child_executor)
    return finalize(study, result, states, network, child_executor)


def finalize(study, result, states, network, child_executor=None):
    result["mode"] = "native"
    context = result["context"]
    result["spatial_artifacts"]["roads"] = network["map"]
    result["network_artifacts"] = network["artifacts"]
    baseline = states[()]
    for option in result["options"]+result["phases"]:
        option["state"] = deepcopy(states[tuple(option["state"]["active_project_ids"])])
        option["traffic_comparison"] = _pair_traffic(baseline, option["state"], context["sha256"])
        option["drainage_comparison"] = _pair_drainage(baseline, option["state"], context["sha256"])
    previous = baseline
    for item, phase in zip(result["marginal_effects"], result["phases"]):
        item["traffic_rows"] = _pair_traffic(previous, phase["state"], context["sha256"])
        item["drainage_rows"] = _pair_drainage(previous, phase["state"], context["sha256"])
        previous = phase["state"]
    result["baseline"] = baseline
    result["standalone_states"] = {identifier: deepcopy(states[(identifier,)]) for identifier in result["standalone_states"]}
    for effect in result["interaction_effects"]:
        key = tuple(effect["active_project_ids"])
        summary = interaction_summary(_pair_drainage(baseline, states[key], context["sha256"]),
                                      [_pair_drainage(baseline, states[(p,)], context["sha256"]) for p in key])
        for name, values in summary.items():
            effect[name].update(values)
    result["validity"] = {"traffic_count_balanced": all(s["traffic"]["count_balanced"] for s in states.values()),
                          "swmm_balance_passed": all(s["drainage"]["balance_passed"] for s in states.values())}
    result["limitations"] = [x for x in result["limitations"] if x not in ("traffic_SUMO", "drainage_SWMM")]
    for item in result["options"]+result["phases"]+result["marginal_effects"]:
        for key, module in (("traffic_comparison", "traffic"), ("traffic_rows", "traffic"), ("drainage_comparison", "drainage"), ("drainage_rows", "drainage")):
            for row in item.get(key, []):
                row.update(source_manifest_id=context["snapshot_manifest_id"],
                           source_ids=list(context["data_coverage"]["modules"][module]["source_ids"]))
    result["ranking"] = comparison.rank(study, result)
    from .normalization import attach
    attach(study, result)
    from .uncertainty import seed_summary, weight_summary
    result["seed_analysis"] = seed_summary(study, result)
    result["weight_analysis"] = weight_summary(study, result)
    from .cache import engines
    result["engine_versions"] = child_executor.versions if child_executor else engines()
    if child_executor:
        result["child_cache"] = {"hits": child_executor.hits, "computed": child_executor.computations,
                                 "engine_versions": child_executor.versions}
    return result
