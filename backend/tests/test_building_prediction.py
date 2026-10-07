import copy
import sys
from pathlib import Path

import pytest

from test_building_scenarios import client
from app.services.simulation.models import BuildingPrediction, ImprovementConstraints
from app.services.simulation.prediction import predict, recommend

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from building_demo import prediction_payload, improvement_constraints


@pytest.fixture
def prediction():
    return predict(BuildingPrediction(**prediction_payload()))


def test_predict_only_requires_existing_state_and_proposed_building(client):
    response = client.post("/api/v1/scenarios/building/predict", json=prediction_payload())
    assert response.status_code == 201
    data = response.json()
    assert set(data["variants"]) == {"baseline", "development"}
    assert "mitigated" not in data["inputs"]
    assert data["recommendations"] == []
    assert data["recommendation_status"] == "not_requested"
    assert data["impact_assessment"]["verdict"] == "worse"
    assert client.get(f"/api/v1/scenarios/building/{data['id']}").json() == data


def test_manual_improved_design_is_not_accepted_as_prediction_input(client):
    payload = prediction_payload()
    payload["mitigated"] = payload["development"]
    assert client.post("/api/v1/scenarios/building/predict", json=payload).status_code == 422


def test_traffic_water_wastewater_and_power_predictions(prediction):
    metrics = prediction["variants"]["development"]
    assert metrics["peak_vehicle_trips_per_hour"] == pytest.approx(80)
    assert metrics["water_demand_m3_per_day"] == pytest.approx(48)
    assert metrics["wastewater_m3_per_day"] == pytest.approx(38.4)
    assert metrics["peak_power_kw"] == pytest.approx(60)
    assert "traffic_queues_and_travel_time" in prediction["unavailable_modules"]
    checks = {item["metric"]: item for item in prediction["impact_assessment"]["targets"]}
    assert checks["water_demand_m3_per_day"]["shortfall"] == pytest.approx(18)


def test_capacity_uses_added_demand_not_total_postdevelopment_demand():
    payload = prediction_payload()
    payload["baseline"]["users"] = 500
    result = predict(BuildingPrediction(**payload))
    check = next(x for x in result["impact_assessment"]["targets"] if x["metric"] == "water_demand_m3_per_day")
    assert check["additional_demand"] == pytest.approx(8)
    assert check["remaining_capacity"] == 30
    assert check["met"]


def test_suggestions_are_generated_preserve_building_and_recalculated(prediction):
    prediction["id"] = "parent-run"
    raw = improvement_constraints(prediction["site_area_m2"])
    raw.update(maximum_additional_storage_m3=400, budget_vnd=2_000_000_000)
    constraints = ImprovementConstraints(**raw)
    original = copy.deepcopy(prediction)
    result = recommend(prediction, constraints)
    assert prediction == original
    assert result["recommendation_status"] == "targets_met"
    best = result["recommendations"][0]
    assert best["assessment"]["targets_met"]
    assert best["predicted"]["peak_vehicle_trips_per_hour"] <= 60 + 1e-7
    assert best["predicted"]["water_demand_m3_per_day"] <= 30 + 1e-7
    assert best["predicted"]["peak_power_kw"] <= 45 + 1e-7
    for candidate in result["recommendations"]:
        assert candidate["estimated_cost_vnd"] <= constraints.budget_vnd + 1e-5
        assert candidate["design"]["paved_m2"] >= constraints.minimum_paved_m2 - 1e-7
        for field in ("roof_m2", "footprint", "floors", "users"):
            assert candidate["design"][field] == prediction["inputs"]["development"][field]
        assert sum(candidate["predicted"]["surfaces_m2"].values()) == pytest.approx(result["site_area_m2"])
        assert candidate["predicted"]["unretained_runoff_m3"] <= prediction["variants"]["development"]["unretained_runoff_m3"]
    changed = constraints.model_copy(update={"budget_vnd": 1000})
    restricted = recommend(prediction, changed)
    assert restricted["recommendation_sha256"] != result["recommendation_sha256"]
    assert restricted["recommendation_status"] != "targets_met"


def test_zero_budget_does_not_invent_free_improvements(prediction):
    prediction["id"] = "parent-run"
    raw = improvement_constraints(prediction["site_area_m2"])
    raw["budget_vnd"] = 0
    result = recommend(prediction, ImprovementConstraints(**raw))
    assert result["recommendations"] == []
    assert result["recommendation_status"] == "no_feasible_improvement"


def test_default_demo_reports_unmet_goal_honestly(prediction):
    prediction["id"] = "parent-run"
    result = recommend(prediction, ImprovementConstraints(**improvement_constraints(prediction["site_area_m2"])))
    assert result["recommendation_status"] == "partial_improvement"
    assert "unretained_runoff_m3" in result["recommendations"][0]["remaining_failures"]


def test_transport_shift_is_not_proposed_without_feasibility_basis(prediction):
    prediction["id"] = "parent-run"
    raw = improvement_constraints(prediction["site_area_m2"])
    raw["transport_shift_feasible"] = False
    result = recommend(prediction, ImprovementConstraints(**raw))
    assert result["recommendations"]
    assert all(x["operations"]["private_vehicle_share"] == .8 for x in result["recommendations"])
    assert result["recommendation_status"] == "partial_improvement"


def test_operational_costs_must_be_explicit(prediction):
    prediction["id"] = "parent-run"
    raw = improvement_constraints(prediction["site_area_m2"])
    del raw["water_cost_vnd_per_saving_point"]
    with pytest.raises(ValueError, match="Explicit"):
        recommend(prediction, ImprovementConstraints(**raw))


def test_unknown_demand_is_not_filled_with_synthetic_factors():
    payload = prediction_payload()
    del payload["demand"]
    result = predict(BuildingPrediction(**payload))
    assert "peak_vehicle_trips_per_hour" not in result["variants"]["development"]
    assert "utility_demand" in result["unavailable_modules"]


@pytest.mark.parametrize("field,value", [("average_vehicle_occupancy",0), ("private_vehicle_share",1.1),
                                        ("remaining_water_m3_per_day",-1), ("basis"," ")])
def test_invalid_demand_factors_rejected(client, field, value):
    payload = prediction_payload()
    payload["demand"][field] = value
    assert client.post("/api/v1/scenarios/building/predict", json=payload).status_code == 422


def test_recommendation_api_preserves_original_and_saves_lineage(client):
    source = client.post("/api/v1/scenarios/building/predict", json=prediction_payload()).json()
    response = client.post(f"/api/v1/scenarios/building/{source['id']}/recommendations",
                           json=improvement_constraints(source["site_area_m2"]))
    assert response.status_code == 201
    result = response.json()
    assert result["id"] != source["id"]
    assert result["parent_run_id"] == source["id"]
    assert client.get(f"/api/v1/scenarios/building/{source['id']}").json() == source
    assert client.get(f"/api/v1/scenarios/building/{result['id']}").json() == result
