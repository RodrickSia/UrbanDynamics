"""Coefficient scope, conservation, capacity sensitivity and actual native reruns."""
from copy import deepcopy
from io import BytesIO
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.integrated_scenarios import demo_payload
from app.services.simulation.integrated import demand, solvers
from app.services.simulation.integrated.context import build_context, digest
from app.services.simulation.integrated.engine import VERSION
from app.services.simulation.integrated.library import parameters
from app.services.simulation.integrated.models import Design, IntegratedRequest, SensitivityRequest
from app.services.simulation.integrated.parameter_catalog import catalog
from app.services.simulation.integrated.sensitivity import analyze_source
from app.services.simulation.store import save


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for key in ("DATABASE_URL", "WAREHOUSE_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    for key, folder in (("DATA_DIR", "data"), ("SIMULATION_SNAPSHOT_DIR", "snapshots"),
                        ("SCENARIO_DATA_DIR", "runs"), ("SIMULATION_WORK_DIR", "engines")):
        monkeypatch.setenv(key, str(tmp_path/folder))


def demand_source(use="residential"):
    # Demand-only tests need an immutable context, not simulated road outputs.
    request = IntegratedRequest(**demo_payload(use))
    frozen = build_context(request)
    return {"id": "test-source", "model_version": VERSION, "workflow": "integrated_building_impact",
            "input_sha256": digest(request.model_dump(mode="json")), "inputs": request.model_dump(mode="json"),
            "context": frozen, "variants": {}, "assessment": {}, "recommendations": []}


def test_office_local_annual_eui_is_converted_and_legacy_demo_retained():
    reviewed = parameters("base")
    assert reviewed["uses"]["office"]["energy_kwh_m2_day"]*365 == pytest.approx(116.4)
    metadata = catalog(reviewed)["parameters"]["uses.office.energy_kwh_m2_day"]
    assert metadata["data_year"] == 2015
    assert metadata["kind"] == "estimated" and metadata["needs_local_calibration"]
    assert metadata["numeric_source"]["original_unit"] == "kWh/m2_floor/year"
    assert parameters("base", "demo")["uses"]["office"]["energy_kwh_m2_day"] == .14


def test_planning_minima_and_citywide_trip_rates_do_not_relabel_defaults():
    library = parameters("base")
    info = catalog(library)
    water = info["parameters"]["uses.residential.water_l_person_day"]
    assert water["value"] == 120 and water["numeric_source"] is None
    assert info["sources"]["qcvn01_2021"]["values"]["domestic_min_l_person_day"] == 80
    assert info["parameters"]["return_fraction"]["numeric_source"] is None
    trips = info["parameters"]["uses.residential.resident_trips_day"]
    assert trips["value"] == 2 and trips["numeric_source"] is None
    assert trips["reference_anchors"][0]["role"] == "citywide_denominator_not_gate_rate"
    assert not library["parameter_validation"]["all_demand_defaults_sourced"]


def test_every_consumed_numeric_demand_coefficient_has_units_scope_and_status():
    library = parameters("base")
    records = catalog(library)["parameters"]
    for use, rates in library["uses"].items():
        for rate in rates:
            record = records[f"uses.{use}.{rate}"]
            assert record["unit"] and record["denominator"] and record["value_status"]
            assert record["value"] == rates[rate]
    for key in ("return_fraction", "reuse_treatment_kwh_m3", "car_occupancy", "ev_hours"):
        assert records[key]["unit"]
    assert library["parameter_validation"]["source_backed_demand_defaults"] == 1


def test_explicit_staff_and_reuse_coefficients_drive_loads_and_keep_ledger():
    design = Design(**demo_payload()["development"])
    design.reuse_m3_day = 10
    lib = parameters("base", "demo")
    base = demand.calculate(design, [1000], lib)
    changed = deepcopy(lib)
    changed["uses"]["residential"]["staff_trips_day"] = 4
    changed["reuse_treatment_kwh_m3"] = 1.6
    result = demand.calculate(design, [1000], changed)
    assert result["person_trips_day"]-base["person_trips_day"] == pytest.approx(24)
    assert result["energy_kwh_day"]-base["energy_kwh_day"] == pytest.approx(10)
    ledger = result["water_ledger"]
    assert ledger["freshwater_m3"]+ledger["reuse_supply_m3"] == pytest.approx(ledger["indoor_and_irrigation_m3"])
    assert ledger["sanitary_discharge_m3"]+ledger["reuse_supply_m3"] == pytest.approx(ledger["sanitary_before_reuse_m3"])


def test_oat_changes_only_selected_rate_and_preserves_source(monkeypatch):
    source = demand_source()
    original = deepcopy(source)
    monkeypatch.setattr(solvers, "traffic", lambda *a: pytest.fail("Demand sensitivity cannot run SUMO"))
    result = analyze_source(source, SensitivityRequest(parameter_ids=["uses.residential.water_l_person_day"]))
    assert source == original
    analysis = result["sensitivity"]
    assert len(analysis["cases"]) == 2
    for case in analysis["cases"]:
        rows = {r["metric"]: r for r in case["rows"]}
        ref = {r["metric"]: r for r in analysis["reference"]["rows"]}
        difference = rows["freshwater_m3_day"]["development"]-ref["freshwater_m3_day"]["development"]
        assert difference == pytest.approx(600*(case["value"]-120)/1000)
        assert rows["wastewater_m3_day"]["development"]-ref["wastewater_m3_day"]["development"] == pytest.approx(difference*.8)
        for metric in ("energy_kwh_day", "person_trips_day", "vehicle_peak_hour"):
            assert rows[metric] == ref[metric]
        assert case["provenance"]["numeric_source"] is None
    assert not analysis["native_engines_recomputed"]


def test_rate_uncertainty_can_flip_capacity_without_changing_pressure_direction():
    source = demand_source()
    source["context"]["library"]["water_spare_m3_day"] = 80
    source["context"]["sha256"] = digest({k: v for k, v in source["context"].items() if k not in ("created_at", "sha256")})
    report = analyze_source(source, SensitivityRequest(parameter_ids=["uses.residential.water_l_person_day"]))["sensitivity"]
    assert not report["capacity_targets_stable"]
    assert "freshwater_m3_day" in report["cases"][1]["target_flips"]
    assert next(row for row in report["stability"] if row["metric"] == "freshwater_m3_day")["verdict_stable"]
    assert not next(row for row in report["target_stability"] if row["metric"] == "freshwater_m3_day")["stable"]


def test_mode_share_bounds_preserve_other_share_and_integer_ev_hours():
    source = demand_source()
    report = analyze_source(source, SensitivityRequest(parameter_ids=["car_person_share", "ev_hours"], high_multiplier=3))["sensitivity"]
    car = next(case for case in report["cases"] if case["parameter_id"] == "car_person_share" and case["level"] == "high")
    assert car["value"] == pytest.approx(.45)
    assert car["value_was_bounded"]
    for case in report["cases"]:
        if case["parameter_id"] == "ev_hours":
            assert isinstance(case["value"], int)


def test_integrity_error_and_no_current_library_import_into_saved_run():
    source = demand_source("office")
    source["context"]["library"] = parameters("base", "demo")
    source["context"].pop("demand_parameter_catalog")
    source["context"]["sha256"] = digest({k: v for k, v in source["context"].items() if k not in ("created_at", "sha256")})
    report = analyze_source(source, SensitivityRequest(parameter_ids=["uses.office.energy_kwh_m2_day"]))["sensitivity"]
    assert report["parameters"][0]["reference"] == .14
    assert report["catalog"]["parameters"]["uses.office.energy_kwh_m2_day"]["numeric_source"] is None
    source["context"]["library"]["return_fraction"] = .5
    with pytest.raises(ValueError, match="integrity"):
        analyze_source(source, SensitivityRequest())


def test_legacy_road_output_mutation_is_recovered_only_when_original_hash_matches():
    source = demand_source()
    source["model_version"] = "integrated-building-1.3"
    original = deepcopy(source)
    for feature in source["context"]["roads"]:
        feature["properties"]["simulated"] = {"speed": 9.5}
    report = analyze_source(source, SensitivityRequest(parameter_ids=["return_fraction"]))["sensitivity"]
    assert report["source_context_integrity"].startswith("legacy_road_output_mutation_recovered")
    assert source["context"]["roads"][0]["properties"]["simulated"] == {"speed": 9.5}
    assert report["reference_context_sha256"] == original["context"]["sha256"]
    source["context"]["library"]["return_fraction"] = .6
    with pytest.raises(ValueError, match="integrity"):
        analyze_source(source, SensitivityRequest(parameter_ids=["return_fraction"]))


@pytest.mark.parametrize("body", [
    {"parameter_ids": ["unknown"]}, {"parameter_ids": ["uses.hospital.energy_kwh_m2_day"]},
    {"parameter_ids": ["uses.residential.water_l_person_day"]*2}, {"low_multiplier": 1},
    {"high_multiplier": 1}, {"mode": "native_traffic"},
    {"mode": "native_traffic", "parameter_ids": ["return_fraction"]},
    {"parameter_ids": ["background_vehicles_hour"]}, {"source_url": "http://localhost/private"},
])
def test_invalid_sensitivity_inputs_rejected_and_parent_unchanged(body):
    source = json.loads(json.dumps(save(demand_source())))
    client = TestClient(app)
    response = client.post(f"/api/v1/scenarios/integrated/{source['id']}/sensitivity", json=body)
    assert response.status_code == 422, response.text
    assert client.get(f"/api/v1/scenarios/integrated/{source['id']}").json() == source


def test_catalog_preflight_and_demand_save_roundtrip(monkeypatch):
    client = TestClient(app)
    assert client.get("/api/v1/scenarios/integrated/parameters").json()["sources"]["office_hcmc_2015"]["year"] == 2015
    assert client.get("/api/v1/scenarios/integrated/parameters?profile=demo").json()["parameters"]["uses.office.energy_kwh_m2_day"]["numeric_source"] is None
    assert client.get("/api/v1/scenarios/integrated/parameters?profile=bad").status_code == 422
    monkeypatch.setattr(solvers, "traffic", lambda *a: pytest.fail("Preflight/demand analysis cannot run SUMO"))
    preflight = client.post("/api/v1/scenarios/integrated/context", json=demo_payload("office"))
    assert preflight.status_code == 200
    assert preflight.json()["demand_parameter_catalog"]["parameters"]["uses.office.energy_kwh_m2_day"]["kind"] == "estimated"
    source = json.loads(json.dumps(save(demand_source())))
    response = client.post(f"/api/v1/scenarios/integrated/{source['id']}/sensitivity", json={})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["context"] == source["context"] and result["input_sha256"] != source["input_sha256"]
    assert result["sensitivity"]["cases"]
    assert client.get(f"/api/v1/scenarios/integrated/{result['id']}").json() == result


def test_real_native_traffic_sensitivity_freezes_hour_and_exports_case_artifacts():
    client = TestClient(app)
    payload = demo_payload()
    payload["data_mode"] = "synthetic"
    response = client.post("/api/v1/scenarios/integrated/predict", json=payload)
    assert response.status_code == 201, response.text
    source = response.json()
    assert source["context"]["sha256"] == digest({k: v for k, v in source["context"].items() if k not in ("created_at", "sha256")})
    assert all("simulated" not in f["properties"] for f in source["context"]["roads"])
    response = client.post(f"/api/v1/scenarios/integrated/{source['id']}/sensitivity", json={
        "mode": "native_traffic", "parameter_ids": ["uses.residential.resident_trips_day"]})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["context"] == source["context"]
    cases = result["sensitivity"]["cases"]
    expected = []
    for case in cases:
        for variant in case["variants"].values():
            assert all(variant["validity"].values())
            assert variant["traffic"]["peak_hour_local"] == source["context"]["traffic_peak_hour"]
            expected.append(variant["traffic"]["artifacts"]["artifact_id"])
    planned = [case["variants"]["development"]["traffic"]["planned_vehicles"] for case in cases]
    assert planned[1] > planned[0]
    archive = client.get(f"/api/v1/scenarios/integrated/{result['id']}/artifacts")
    assert archive.status_code == 200, archive.text
    with zipfile.ZipFile(BytesIO(archive.content)) as bundle:
        assert bundle.testzip() is None
        assert len(bundle.namelist()) == len(set(bundle.namelist()))
        assert all(any(name.startswith(identifier+"/") for name in bundle.namelist()) for identifier in expected)
        assert json.loads(bundle.read("scenario.json"))["sensitivity"]["reference_context_sha256"] == source["context"]["sha256"]
