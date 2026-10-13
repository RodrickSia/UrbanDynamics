from copy import deepcopy

from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.engine import run_screening


def test_fixed_shadow_receiver_union_and_baseline_removal():
    payload = demo_study("cumulative")
    result = run_screening(PlanningStudy(**payload))
    options = {o["id"]: o["state"] for o in result["options"]}
    baseline = result["baseline"]["shadow"]
    assert baseline["metrics"]["mean_shaded_receiver_m2"] == 0
    for state in options.values():
        shadow = state["shadow"]
        assert shadow["receiver_area_m2"] == baseline["receiver_area_m2"]
        assert all(0 <= r["shaded_receiver_m2"] <= shadow["receiver_area_m2"] for r in shadow["hourly"])
        assert all(f["geometry"]["type"] in ("Polygon", "MultiPolygon") for f in shadow["map"]["features"])
    assert options["ABC"]["metrics"]["mean_shaded_receiver_m2"] > options["A_only"]["metrics"]["mean_shaded_receiver_m2"]
    payload["projects"][0]["baseline"] = deepcopy(payload["projects"][0]["development"])
    payload["projects"][0]["baseline"]["buildings"][0]["height_m"] = 80
    changed = run_screening(PlanningStudy(**payload))
    state_a = next(o["state"] for o in changed["options"] if o["id"] == "A_only")
    assert state_a["metrics"]["mean_shaded_receiver_m2"] == options["A_only"]["metrics"]["mean_shaded_receiver_m2"]
    assert changed["baseline"]["metrics"]["mean_shaded_receiver_m2"] > state_a["metrics"]["mean_shaded_receiver_m2"]


def test_pareto_weights_explicit_and_missing_native_metrics_block_ranking():
    payload = demo_study()
    assert run_screening(PlanningStudy(**payload))["ranking"]["status"] == "not_requested"
    payload["criteria"] = [{"metric": "power_peak_kw", "direction": "minimize", "weight": 1},
                           {"metric": "school_unserved_students", "direction": "minimize", "weight": 2}]
    result = run_screening(PlanningStudy(**payload))
    assert result["ranking"]["status"] == "scenario_only"
    assert result["ranking"]["pareto_option_ids"]
    assert all(0 <= row["score"] <= 1 for row in result["ranking"]["weighted_scores"])
    payload["criteria"].append({"metric": "background_completed_delay_seconds", "direction": "minimize", "weight": 1})
    blocked = run_screening(PlanningStudy(**payload))["ranking"]
    assert blocked["status"] == "insufficient_data"
    assert blocked["pareto_option_ids"] == []


def test_unknown_service_does_not_win_with_invented_zero():
    payload = demo_study()
    payload["school_facilities"][0]["capacity_places"] = None
    payload["criteria"] = [{"metric": "school_unserved_students", "direction": "minimize"}]
    rank = run_screening(PlanningStudy(**payload))["ranking"]
    assert rank["status"] == "insufficient_data"
    assert len(rank["missing"]) == 3


def test_unknown_occupancy_masks_portfolio_interaction_but_preserves_assumptions():
    payload = demo_study("cumulative")
    payload["projects"][0]["baseline_occupancy"] = "unknown"
    result = run_screening(PlanningStudy(**payload))
    for effect in result["interaction_effects"]:
        for metric in ("residents", "power_peak_kw", "person_trips_day"):
            assert effect["metrics"][metric] is None
            assert effect["comparability_by_metric"][metric] == "insufficient_data"
            assert effect["unavailable_reasons"][metric]
            assert effect["scenario_values"][metric]["value"] is not None
        assert effect["metrics"]["impervious_m2"] is not None


def test_invalid_constituent_blocks_interaction_even_if_combined_run_is_valid():
    from app.services.simulation.planning.engine import interaction_summary
    good = {"metric": "node_flooding_m3", "delta": 10., "comparability": "scenario_only"}
    invalid = {**good, "delta": 3., "comparability": "not_comparable"}
    missing = {**good, "delta": None, "comparability": "insufficient_data"}
    result = interaction_summary([good], [[invalid], [good]])
    assert result["metrics"]["node_flooding_m3"] is None
    assert result["comparability_by_metric"]["node_flooding_m3"] == "not_comparable"
    assert result["scenario_values"]["node_flooding_m3"]["value"] == -3
    assert interaction_summary([good], [[missing]])["scenario_values"]["node_flooding_m3"]["value"] is None
