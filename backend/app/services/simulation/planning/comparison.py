"""Explicit criteria and Pareto trade-offs; missing data never wins a rank."""


def rank(study, result):
    if not study.criteria:
        return {"status": "not_requested", "note": "Choose criteria to obtain Pareto alternatives; no default overall winner."}
    values, missing = {}, []
    for option in result["options"]:
        values[option["id"]] = {}
        for criterion in study.criteria:
            metric = criterion.metric
            rows = option["comparison"]+option.get("drainage_comparison", [])
            if metric == "background_completed_delay_seconds":
                rows = [r for r in option.get("traffic_comparison", []) if r["metric"] == metric]
            else:
                rows = [r for r in rows if r["metric"] == metric]
            if not rows or any(r["after"] is None or r["comparability"] not in ("scenario_only", "comparable") for r in rows):
                missing.append({"option_id": option["id"], "metric": metric, "reason": "Missing or invalid/incomparable metric"})
                continue
            values[option["id"]][metric] = sum(r["after"] for r in rows)/len(rows)
    criteria = [c.model_dump(mode="json") for c in study.criteria]
    if missing:
        return {"status": "insufficient_data", "criteria": criteria, "missing": missing, "pareto_option_ids": [],
                "note": "All requested criteria must be available for all options; no score from substituted zeros."}
    def dominates(left, right):
        differences = [(values[left][c.metric]-values[right][c.metric])*(1 if c.direction == "minimize" else -1) for c in study.criteria]
        return all(d <= 1e-9 for d in differences) and any(d < -1e-9 for d in differences)
    pareto = [identifier for identifier in sorted(values) if not any(dominates(other, identifier) for other in values if other != identifier)]
    scores = []
    if all(c.weight is not None for c in study.criteria):
        total_weight = sum(c.weight for c in study.criteria)
        for identifier in sorted(values):
            score, contributions = 0.0, {}
            for criterion in study.criteria:
                column = [v[criterion.metric] for v in values.values()]
                lo, hi = min(column), max(column)
                benefit = (values[identifier][criterion.metric]-lo)/(hi-lo) if hi > lo else 0.5
                if criterion.direction == "minimize":
                    benefit = 1-benefit
                contribution = benefit*criterion.weight/total_weight
                contributions[criterion.metric] = contribution
                score += contribution
            scores.append({"option_id": identifier, "score": score, "contributions": contributions})
        scores.sort(key=lambda r: (-r["score"], r["option_id"]))
    return {"status": "scenario_only", "criteria": criteria, "values": values,
            "pareto_option_ids": pareto, "weighted_scores": scores,
            "normalization": "Min-max over these alternatives only; ties receive 0.5; weights normalized to sum one.",
            "traffic_aggregation": "Equal mean of requested hour/seed scenario results, not a population-weighted daily forecast.",
            "note": "Pareto is relative to chosen benefits/pressures; synthetic capacities cannot justify planning approval. Weighted scores require stability checks."}
