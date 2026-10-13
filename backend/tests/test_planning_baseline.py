from copy import deepcopy

import pytest

from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.presets import demo_study, rehousing_study


def relocation_input():
    payload = demo_study("cumulative")
    origin, target = payload["projects"][0], payload["projects"][2]
    origin["baseline"] = deepcopy(origin["development"])
    origin["baseline"]["buildings"][0].update(name="Existing homes", residents=100, units=40)
    origin["baseline_occupancy"] = "known"
    origin["development"] = deepcopy(payload["projects"][1]["baseline"])
    # The emptied origin needs its own parcel's area, not another parcel's.
    origin["development"] = {**deepcopy(origin["baseline"]), "buildings": []}
    origin["development"].update(ev_chargers=0, parking_spaces=0)
    from app.services.simulation.integrated.geometry import analyze
    from app.services.simulation.integrated.models import Design
    from app.services.simulation.models import PolygonInput
    roof = analyze(PolygonInput(**origin["site"]), Design(**origin["baseline"]))["metrics"]["surfaces_m2"]["roof"]
    origin["development"]["green_m2"] += roof
    target["development"]["buildings"][0]["residents"] = 300
    payload["resident_transfers"] = [{"id": "move_A_C", "from_project_id": "A", "to_project_id": "C",
                                      "residents": 100, "when_active_project_ids": ["A", "C"],
                                      "source": "Synthetic rehousing plan: 100 existing residents are included in C's 300 residents"}]
    return payload


def test_relocation_conserves_people_and_does_not_add_demand_twice():
    payload = relocation_input()
    result = run_screening(PlanningStudy(**payload))
    state = next(o["state"] for o in result["options"] if o["id"] == "ABC")
    ledger = state["baseline_ledger"]
    assert ledger["population"]["baseline"] == 1300
    assert ledger["population"]["final"] == 1500
    assert ledger["population"]["net_delta"] == 200
    assert ledger["population"]["declared_internal_relocated"] == 100
    assert not ledger["unresolved_existing_residents"]
    without = deepcopy(payload)
    without["resident_transfers"] = []
    other = next(o["state"] for o in run_screening(PlanningStudy(**without))["options"] if o["id"] == "ABC")
    assert state["metrics"] == other["metrics"]
    assert state["school_services"] == other["school_services"]
    assert state["hourly_power_kw"] == other["hourly_power_kw"]
    assert other["baseline_ledger"]["unresolved_existing_residents"][0]["residents"] == 100
    for row in ledger["parcels"]:
        for value in row["loads"].values():
            assert value["baseline"]-value["accounting_removed"]+value["replacement_added"] == pytest.approx(value["final"])
        profile = row["hourly_power_kw"]
        assert [a-b+c for a,b,c in zip(profile["baseline"], profile["accounting_removed"], profile["replacement_added"])] == pytest.approx(profile["final"])
    for metric, value in ledger["regional_loads"].items():
        assert value["regional_final"] == pytest.approx(state["metrics"][metric])


def test_transfer_capacity_overlap_and_unknown_origin_validation():
    payload = relocation_input()
    payload["resident_transfers"][0]["residents"] = 101
    with pytest.raises(ValueError, match="baseline residents"):
        PlanningStudy(**payload)
    payload = relocation_input()
    payload["resident_transfers"].append({**deepcopy(payload["resident_transfers"][0]), "id": "duplicate_move"})
    with pytest.raises(ValueError, match="baseline residents"):
        PlanningStudy(**payload)
    payload = relocation_input()
    payload["resident_transfers"][0]["from_project_id"] = None
    payload["resident_transfers"][0]["residents"] = 301
    with pytest.raises(ValueError, match="final residents"):
        PlanningStudy(**payload)
    payload = relocation_input()
    payload["projects"][0]["baseline_occupancy"] = "unknown"
    with pytest.raises(ValueError, match="declared baseline occupancy"):
        PlanningStudy(**payload)


def test_retained_building_unknown_and_transfer_hash_order():
    payload = demo_study("cumulative")
    project = payload["projects"][0]
    project["baseline"] = deepcopy(project["development"])
    # Default height 36 and explicitly parsed 36.0 are the same building.
    del project["baseline"]["buildings"][0]["height_m"]
    state = run_screening(PlanningStudy(**payload))["options"][0]["state"]
    retained = next(r for r in state["baseline_ledger"]["parcels"] if r["project_id"] == "A")
    assert retained["retained_buildings"] == ["Project A"]
    assert retained["retained_residents"] == 600
    assert not retained["removed_or_remodeled_buildings"]
    assert not state["baseline_ledger"]["unresolved_existing_residents"]
    project["baseline_occupancy"] = "unknown"
    ledger = run_screening(PlanningStudy(**payload))["baseline"]["baseline_ledger"]
    assert ledger["population"]["certainty"] == "unknown"
    assert ledger["regional_loads"]["freshwater_m3_day"]["certainty"] == "unknown"
    payload = relocation_input()
    first = build_context(PlanningStudy(**payload))
    payload["resident_transfers"][0]["when_active_project_ids"].reverse()
    assert first == build_context(PlanningStudy(**payload))


def test_native_transfer_uses_final_design_once_and_keeps_ledger(tmp_path, monkeypatch):
    from app.services.simulation.planning.native import run_native
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path))
    payload = relocation_input()
    payload["projects"] = [payload["projects"][0], payload["projects"][2]]
    payload["options"] = [{"id": "AC", "title": "Rehousing A into C", "active_project_ids": ["A", "C"]}]
    payload["phases"] = []
    payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    result = run_native(PlanningStudy(**payload))
    state = result["options"][0]["state"]
    assert all(result["validity"].values())
    assert state["baseline_ledger"]["population"]["declared_internal_relocated"] == 100
    assert state["metrics"]["residents"] == 1500
    traffic = state["traffic"]["runs"][0]
    expected = payload.get("background_vehicles_hour", 400)+sum(round(p["demand"]["hourly"][kind][18]) for p in state["parcels"] for kind in ("cars", "motorcycles"))
    assert traffic["planned_vehicles"] == expected
    assert traffic["count_balanced"]


def test_rehousing_demo_declared_flow_balances_and_stage_uncertainty():
    result = run_screening(PlanningStudy(**rehousing_study()))
    full = next(o["state"] for o in result["options"] if o["id"] == "ABC")
    population = full["baseline_ledger"]["population"]
    assert population["net_delta"] == 200
    assert population["declared_internal_relocated"] == 100
    assert population["declared_external_inflow"] == 200
    assert population["unexplained_net_change"] == 0
    assert not full["baseline_ledger"]["unresolved_existing_residents"]
    cleared = next(o["state"] for o in result["options"] if o["id"] == "A_only")
    assert cleared["baseline_ledger"]["unresolved_existing_residents"][0]["residents"] == 100
    assert result["phases"][1]["state"] == next(o["state"] for o in result["options"] if o["id"] == "AC")


def test_api_zip_exports_ledger_with_units_and_source(tmp_path, monkeypatch):
    import csv
    import io
    import zipfile
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.simulation.planning.jobs import process_one
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"ledger.sqlite"))
    client = TestClient(app)
    response = client.post("/api/v1/planning/studies", json=rehousing_study())
    assert response.status_code == 201, response.text
    study = response.json()
    client.post(f"/api/v1/planning/studies/{study['id']}/runs", json={"mode": "screening", "idempotency_key": "ledger-export"})
    completed = process_one()
    assert completed["status"] == "succeeded", completed
    response = client.get(f"/api/v1/planning/runs/{completed['result_id']}/artifacts")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("baseline-ledger.csv").decode("utf-8-sig"))))
    assert {r["option_id"] for r in rows} >= {"baseline", "ABC", "phase_1", "phase_2", "phase_3"}
    assert all(r["baseline_source"] and r["unit"] and r["certainty"] for r in rows)
    for row in rows:
        assert float(row["baseline"])-float(row["accounting_removed"])+float(row["replacement_added"]) == pytest.approx(float(row["final"]))
