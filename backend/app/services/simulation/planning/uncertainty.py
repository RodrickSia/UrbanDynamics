"""Paired seed variability and declared assumption/weight sensitivity.

Ranges are observed scenario ranges, never confidence intervals. Each case
freezes its own shared baseline and evaluates unchanged building programs.
"""
from copy import deepcopy
from itertools import combinations

from .models import PlanningStudy
from .context import build_context, canonical_input
from .comparison import rank


VALID = ("scenario_only", "comparable")


def effective_studies(study):
    settings = study.uncertainty
    if settings is None:
        raise ValueError("Uncertainty analysis requires declared uncertainty settings")
    original = canonical_input(study)
    output = []
    for case in [None]+sorted(settings.cases, key=lambda c: c.id):
        document = deepcopy(original)
        document["conditions"]["seeds"] = sorted(settings.seeds)
        changes = case.model_dump(exclude={"id", "source"}, exclude_none=True) if case else {}
        for key in ("level", "rainfall_mm"):
            if key in changes:
                document["conditions"][key] = changes[key]
        for key in ("background_vehicles_hour", "school_age_fraction"):
            if key in changes:
                document[key] = changes[key]
        snapshot = document["background_snapshot"]
        if "background_vehicles_hour" in changes and document["traffic_prior"] and not (snapshot and "traffic" in snapshot["included_modules"]):
            prior = document["traffic_prior"]
            peak = max(a+b for a,b in zip(prior["cars"], prior["motorcycles"]))
            target = changes["background_vehicles_hour"]
            if peak == 0 and target > 0:
                raise ValueError("Cannot scale a zero traffic prior to positive peak without a declared vehicle mix/profile")
            for hour in range(24):
                cars, bikes = prior["cars"][hour], prior["motorcycles"][hour]
                total = round((cars+bikes)*target/peak) if peak else 0
                prior["cars"][hour] = round(total*cars/(cars+bikes)) if cars+bikes else 0
                prior["motorcycles"][hour] = total-prior["cars"][hour]
            prior["source"] = f"Sensitivity case {case.id}: assumed peak {target} vehicles/h; hourly shape and conditional vehicle mix retained. " + prior["source"][:750]
            prior["source_kind"] = "estimated"
        if "background_vehicles_hour" in changes and snapshot and "traffic" in snapshot["included_modules"]:
            from .background import resolve
            clean = resolve(study)["traffic"]
            target = changes["background_vehicles_hour"]
            for hour in range(24):
                total = clean["cars"][hour]+clean["motorcycles"][hour]
                cars = round(target*clean["cars"][hour]/total) if total else round(target*.25)
                for kind, value in (("cars", cars), ("motorcycles", target-cars)):
                    removed = sum(p["traffic"][kind][hour] for p in snapshot["parcels"])
                    snapshot["regional_traffic"][kind][hour] = value+removed
            snapshot["source"] = f"Synthetic traffic sensitivity case {case.id}; based on snapshot {snapshot['id']}"
            snapshot["source_kind"] = "synthetic"
        if "utility_capacity_scale" in changes:
            for zone in document["utility_zones"]:
                for key in ("power_capacity_kw", "water_capacity_m3_day", "wastewater_capacity_m3_day"):
                    if zone[key] is not None:
                        zone[key] *= changes["utility_capacity_scale"]
        if "existing_school_capacity_scale" in changes:
            for facility in document["school_facilities"]:
                if facility["capacity_places"] is not None:
                    facility["capacity_places"] = round(facility["capacity_places"]*changes["existing_school_capacity_scale"])
        # Unknown values stay unknown. No changes to project/design/baseline,
        # program targets or reserved enrollment are silently made to fit cases.
        output.append(("reference" if case is None else case.id,
                       "Unchanged input with the declared paired seed suite" if case is None else case.source,
                       changes, PlanningStudy(**document)))
    return output


def spread(values, expected, threshold=None):
    missing = any(v is None for v in values)
    available = [v for v in values if v is not None]
    status = "insufficient_data" if missing else "insufficient_seed_suite" if len(available) < 3 or len(available) != expected else "sampled"
    result = {"status": status, "n": len(available), "expected_n": expected,
              "min": min(available) if available else None, "max": max(available) if available else None,
              "mean": sum(available)/len(available) if available else None,
              "range_kind": "observed paired-seed range, not a confidence interval"}
    if threshold is not None:
        result["material_delta_seconds"] = threshold
        if status != "sampled":
            result["delta_stability"] = status
        elif all(abs(v) <= threshold for v in available):
            result["delta_stability"] = "within_material_threshold"
        elif all(v > threshold for v in available):
            result["delta_stability"] = "positive_in_all_sampled_seeds"
        elif all(v < -threshold for v in available):
            result["delta_stability"] = "negative_in_all_sampled_seeds"
        else:
            result["delta_stability"] = "changes_sign_or_crosses_material_threshold"
    return result


def seed_summary(study, result):
    seeds = sorted(study.conditions.seeds)
    threshold = study.uncertainty.traffic_material_delta_seconds if study.uncertainty else .5
    summaries = []
    for option in result["options"]:
        rows = option.get("traffic_comparison", [])
        for hour in sorted(study.conditions.traffic_hours):
            for metric in sorted({r["metric"] for r in rows}):
                lookup = {r["seed"]: r for r in rows if r["hour_local"] == hour and r["metric"] == metric}
                values = [lookup[s]["delta"] if s in lookup and lookup[s]["comparability"] in VALID else None for s in seeds]
                summaries.append({"option_id": option["id"], "hour_local": hour, "metric": metric,
                                  "paired_seed_deltas": [{"seed": s, "delta": v} for s, v in zip(seeds, values)],
                                  **spread(values, len(seeds), threshold if metric.endswith("delay_seconds") else None)})
    pairs = []
    for left, right in combinations(result["options"], 2):
        for hour in sorted(study.conditions.traffic_hours):
            a = {r["seed"]: r for r in left.get("traffic_comparison", []) if r["hour_local"] == hour and r["metric"] == "background_completed_delay_seconds"}
            b = {r["seed"]: r for r in right.get("traffic_comparison", []) if r["hour_local"] == hour and r["metric"] == "background_completed_delay_seconds"}
            values = [a[s]["after"]-b[s]["after"] if s in a and s in b and a[s]["comparability"] in VALID and b[s]["comparability"] in VALID else None for s in seeds]
            pairs.append({"left_option_id": left["id"], "right_option_id": right["id"], "hour_local": hour,
                          "metric": "background_completed_delay_seconds", "meaning": "left minus right on the same hour and seed",
                          "paired_seed_deltas": [{"seed": s, "delta": v} for s, v in zip(seeds, values)],
                          **spread(values, len(seeds), threshold)})
    ranks = []
    for seed in seeds:
        view = {"options": []}
        for option in result["options"]:
            view["options"].append({**option, "traffic_comparison": [r for r in option.get("traffic_comparison", []) if r["seed"] == seed]})
        ranks.append({"seed": seed, "ranking": rank(study, view)})
    return {"kind": "solver_stochastic_variation", "seed_suite": seeds,
            "status": "sampled" if len(seeds) >= 3 else "insufficient_seed_suite",
            "paired_deltas": summaries, "option_pairs": pairs, "rankings_by_seed": ranks,
            "ranking_stability": ranking_stability(ranks, minimum_count=3),
            "note": "Paired cases share background/project departure streams. Three seeds are a demo stability check, not local validation. Overall completed-trip means also change with trip mix; prefer the background cohort for impact decisions."}


def ranking_stability(items, minimum_count=2):
    rankings = [item["ranking"] for item in items]
    if not rankings or any(r["status"] not in VALID for r in rankings):
        return {"status": "insufficient_data_or_no_criteria"}
    if len(rankings) < minimum_count:
        return {"status": "insufficient_samples", "n": len(rankings), "required_n": minimum_count}
    pareto_sets = [tuple(sorted(r["pareto_option_ids"])) for r in rankings]
    tops = []
    for ranking in rankings:
        scores = ranking.get("weighted_scores", [])
        if scores:
            tops.append(tuple(sorted(r["option_id"] for r in scores if abs(r["score"]-scores[0]["score"]) <= 1e-9)))
    return {"status": "sampled", "pareto_membership_stable": len(set(pareto_sets)) == 1,
            "weighted_top_set_stable": len(set(tops)) == 1 if len(tops) == len(rankings) else None,
            "note": "Stability holds only for the evaluated scenarios; tied top scores remain a set, not an arbitrary ID winner."}


def weight_summary(study, result):
    if not study.criteria or any(c.weight is None for c in study.criteria):
        return {"status": "not_requested", "note": "No weighted criteria"}
    samples = [{"id": "declared", "weights": {c.metric: c.weight for c in study.criteria}, "ranking": rank(study, result)}]
    for criterion in study.criteria:
        for factor in (.5, 2):
            # Ratios matter; normalizing back to a max of 100 preserves relative
            # weights and the public schema bound for a declared weight of 100.
            document = study.model_dump(mode="json")
            for c in document["criteria"]:
                if c["metric"] == criterion.metric:
                    c["weight"] *= factor
            maximum = max(c["weight"] for c in document["criteria"])
            if maximum > 100:
                for c in document["criteria"]:
                    c["weight"] *= 100/maximum
            variant = PlanningStudy(**document)
            samples.append({"id": f"{criterion.metric}_x{factor}", "weights": {c.metric: c.weight for c in variant.criteria}, "ranking": rank(variant, result)})
    return {"status": "sampled", "method": "One criterion weight at a time at 0.5x and 2x; same simulation outputs",
            "samples": samples, "ranking_stability": ranking_stability(samples)}


def run(study, checkpoint=None, child_executor=None):
    from .engine import run_screening
    from .native import run_native
    settings = study.uncertainty
    variants = effective_studies(study)
    cases = []
    for index, (identifier, source, changes, variant) in enumerate(variants):
        def progress(value):
            if checkpoint:
                checkpoint({**value, "assumption_case_id": identifier, "case_index": index, "case_count": len(variants)})
        progress({"module": "assumption_case"})
        result = run_native(variant, progress, child_executor) if settings.engine == "native" else run_screening(variant, progress)
        result.setdefault("weight_analysis", weight_summary(variant, result))
        cases.append({"id": identifier, "source": source, "changes": changes,
                      "context_hash": result["context"]["sha256"], "result": result})
    # The familiar primary result is the actual reference effective input (with
    # the requested seed suite), not the initial one-seed request relabeled.
    primary = deepcopy(cases[0]["result"])
    primary["mode"] = "uncertainty"
    primary["analysis_request"] = canonical_input(study)
    primary["analysis_request_context_hash"] = build_context(study)["sha256"]
    primary["assumption_cases"] = cases
    metric_ranges = []
    for option in primary["options"]:
        for metric in option["state"]["metrics"]:
            values = []
            for case in cases:
                other = next(o for o in case["result"]["options"] if o["id"] == option["id"])
                rows = other["comparison"]+other.get("drainage_comparison", [])
                row = next((r for r in rows if r["metric"] == metric), None)
                values.append(row["delta"] if row and row["comparability"] in VALID else None)
            valid = [v for v in values if v is not None]
            metric_ranges.append({"option_id": option["id"], "metric": metric,
                                  "case_deltas": [{"case_id": c["id"], "delta": v} for c, v in zip(cases, values)],
                                  "min_delta": min(valid) if valid else None, "max_delta": max(valid) if valid else None,
                                  "status": "sampled_scenario_range" if len(valid) == len(cases) else "insufficient_data"})
    primary["uncertainty_analysis"] = {"kind": "declared_input_assumption_sensitivity", "engine": settings.engine,
        "case_ids": [c["id"] for c in cases], "metric_delta_ranges": metric_ranges,
        "ranking_stability_across_cases": ranking_stability([{"ranking": c["result"]["ranking"]} for c in cases]),
        "weights": weight_summary(study, primary),
        "limits": "Cases are explicit scenarios, not probabilities or confidence intervals. Building plans stay fixed. Within each case use its paired-seed summary; do not combine input and solver ranges into one uncertainty claim."}
    traffic_ranges = []
    for option in primary["options"]:
        for hour in sorted(study.conditions.traffic_hours):
            for metric in ("background_completed_delay_seconds", "max_queue_length_m"):
                means = []
                for case in cases:
                    sampled = next((r for r in case["result"].get("seed_analysis", {}).get("paired_deltas", [])
                                    if r["option_id"] == option["id"] and r["hour_local"] == hour and r["metric"] == metric), None)
                    means.append(sampled["mean"] if sampled and sampled["status"] == "sampled" else None)
                valid = [v for v in means if v is not None]
                traffic_ranges.append({"option_id": option["id"], "hour_local": hour, "metric": metric,
                                       "case_mean_paired_deltas": [{"case_id": c["id"], "mean_delta": v} for c, v in zip(cases, means)],
                                       "min_case_mean_delta": min(valid) if valid else None,
                                       "max_case_mean_delta": max(valid) if valid else None,
                                       "status": "sampled_scenario_range" if len(valid) == len(cases) else "insufficient_data",
                                       "note": "Range over case means is input-scenario sensitivity; within-case paired seed spread is stored separately."})
    primary["uncertainty_analysis"]["traffic_case_mean_ranges"] = traffic_ranges
    capacity_cases = []
    for option in primary["options"]:
        for zone in option["state"]["utility_zones"]:
            for check in zone["checks"]:
                statuses = []
                for case in cases:
                    state = next(o["state"] for o in case["result"]["options"] if o["id"] == option["id"])
                    other_zone = next(z for z in state["utility_zones"] if z["id"] == zone["id"])
                    other = next(c for c in other_zone["checks"] if c["metric"] == check["metric"])
                    statuses.append({"case_id": case["id"], "status": other["status"], "capacity": other["capacity"], "load": other["value"]})
                unknown = any(c["status"] == "unknown" for c in statuses)
                capacity_cases.append({"option_id": option["id"], "zone_id": zone["id"], "metric": check["metric"],
                                       "case_checks": statuses, "status": "insufficient_data" if unknown else "sensitive_in_sampled_cases" if len({c["status"] for c in statuses}) > 1 else "stable_in_sampled_cases"})
    primary["uncertainty_analysis"]["capacity_stability"] = capacity_cases
    reasons, incomplete = [], False
    case_stability = primary["uncertainty_analysis"]["ranking_stability_across_cases"]
    if case_stability["status"] != "sampled":
        incomplete = True
    elif not case_stability["pareto_membership_stable"] or case_stability["weighted_top_set_stable"] is False:
        reasons.append("input_assumptions")
    if settings.engine == "native":
        for case in cases:
            stability = case["result"]["seed_analysis"]["ranking_stability"]
            if stability["status"] != "sampled":
                incomplete = True
            elif not stability["pareto_membership_stable"] or stability["weighted_top_set_stable"] is False:
                reasons.append("solver_seed:"+case["id"])
    for case in cases:
        weights = case["result"]["weight_analysis"]
        if weights["status"] == "sampled":
            stability = weights["ranking_stability"]
            if stability["status"] != "sampled":
                incomplete = True
            elif stability["weighted_top_set_stable"] is False:
                reasons.append("criterion_weights:"+case["id"])
    primary["uncertainty_analysis"]["overall_ranking_assessment"] = {
        "status": "insufficient_data_or_no_criteria" if incomplete else "sensitive_in_sampled_cases" if reasons else "stable_in_sampled_cases",
        "sensitivity_sources": sorted(set(reasons)),
        "note": "Stable case means alone are insufficient when per-seed rankings change. Stability does not prove a globally optimal or locally validated planning decision."}
    return primary
