import copy
import io
import json
import zipfile
import hashlib
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolate_published_background(monkeypatch, tmp_path):
    # Regression fixtures must not pick up the user's downloaded pilot snapshots.
    monkeypatch.setenv("SIMULATION_SNAPSHOT_DIR", str(tmp_path/"snapshots"))

from app.main import app
from app.routers.integrated_scenarios import demo_payload
from app.services.simulation.integrated import engine, geometry, solvers
from app.services.simulation.integrated.context import build_context
from app.services.simulation.integrated.demand import calculate
from app.services.simulation.integrated.models import IntegratedRequest, Design, RecommendationRequest


@pytest.fixture(scope="module")
def real_run(tmp_path_factory):
    directory = tmp_path_factory.mktemp("integrated")
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("WAREHOUSE_PASSWORD", raising=False); patch.delenv("DATABASE_URL", raising=False)
        patch.setenv("SCENARIO_DATA_DIR", str(directory/"runs"))
        patch.setenv("SIMULATION_WORK_DIR", str(directory/"engines"))
        patch.setenv("DATA_DIR", str(directory/"no-data"))
        client = TestClient(app)
        response = client.post("/api/v1/scenarios/integrated/predict", json=demo_payload())
        assert response.status_code == 201, response.text
        yield client, response.json(), directory


@pytest.mark.parametrize("use", ["residential", "school", "office", "hospital", "other"])
def test_presets_have_consistent_geometry_and_separate_population(use):
    request = IntegratedRequest(**demo_payload(use))
    context = build_context(request)
    geom = geometry.analyze(request.site, request.development)
    result = calculate(request.development, geom["floor_areas"], context["library"])
    assert sum(geom["metrics"]["surfaces_m2"].values()) == pytest.approx(context["site_area_m2"])
    assert result["residents"] == (600 if use == "residential" else 0)
    assert result["daily_visitors"] > 0
    assert len(result["hourly"]["power_kw"]) == 24
    assert sum(result["hourly"]["power_kw"]) == pytest.approx(result["energy_kwh_day"])
    assert sum(result["hourly"]["water_m3"]) == pytest.approx(result["freshwater_m3_day"])


def test_water_reuse_irrigation_and_stagger_conservation():
    request = IntegratedRequest(**demo_payload())
    context = build_context(request)
    floor = geometry.analyze(request.site, request.development)["floor_areas"]
    base = calculate(request.development, floor, context["library"])
    changed = request.development.model_copy(update={"reuse_m3_day": 10000, "stagger_hours": 3})
    revised = calculate(changed, floor, context["library"])
    assert revised["reused_m3_day"] <= base["wastewater_m3_day"]
    assert revised["wastewater_m3_day"] >= -1e-8
    assert revised["person_trips_day"] == pytest.approx(base["person_trips_day"])
    assert revised["water_ledger"]["freshwater_m3"]+revised["reused_m3_day"] == pytest.approx(base["freshwater_m3_day"])
    assert base["wastewater_m3_day"] == pytest.approx((base["freshwater_m3_day"]-base["irrigation_m3_day"])*.8)


def test_area_overlap_and_invalid_schedule_rejected_before_solver(monkeypatch):
    payload = demo_payload()
    payload["development"]["buildings"].append(copy.deepcopy(payload["development"]["buildings"][0]))
    monkeypatch.setattr(solvers, "traffic", lambda *a: pytest.fail("Must validate before solver"))
    with pytest.raises(ValueError, match="overlap"):
        engine.predict(IntegratedRequest(**payload))
    payload = demo_payload()
    payload["development"]["buildings"][0]["activity_profile"] = [0]*24
    assert TestClient(app).post("/api/v1/scenarios/integrated/predict", json=payload).status_code == 422


def test_canopy_union_and_shadow_respond_to_height():
    request = IntegratedRequest(**demo_payload())
    single = geometry.analyze(request.site, request.development)
    doubled = request.development.model_copy(deep=True)
    doubled.trees += copy.deepcopy(doubled.trees)
    assert geometry.analyze(request.site, doubled)["metrics"]["canopy_m2"] == pytest.approx(single["metrics"]["canopy_m2"])
    shadow = geometry.shadows(single, request.development, request.conditions)
    higher = request.development.model_copy(deep=True)
    higher.buildings[0].height_m *= 2
    revised = geometry.shadows(geometry.analyze(request.site, higher), higher, request.conditions)
    assert revised["mean_outdoor_shaded_percent"] > shadow["mean_outdoor_shaded_percent"]
    assert "air temperature" in shadow["limitations"]


def test_real_solvers_and_immutable_storage_roundtrip(real_run):
    client, result, directory = real_run
    assert client.get(f"/api/v1/scenarios/integrated/{result['id']}").json() == result
    for state in result["variants"].values():
        t, d = state["traffic"], state["drainage"]
        assert t["engine"] == "SUMO"
        assert t["planned_vehicles"] == t["completed_vehicles"]+t["unfinished_vehicles"]+t["undeparted_vehicles"]
        assert t["collisions"] == 0
        assert d["engine"] == "SWMM" and d["balance_passed"]
        assert d["runoff_peak_m3_s"] > 0
        assert state["validity"]["traffic_count_balanced"]
        assert len(d["timeseries"]["runoff_m3_s"]) > 0
        assert len(d["timeseries"]["minute"]) == len(d["timeseries"]["runoff_m3_s"])
        assert (directory/"engines"/t["artifacts"]["artifact_id"]/"network.xml").is_file()
    assert result["assessment"]["verdict"] == "mixed"
    assert "housing_units" in result["assessment"]["benefits"]
    assert result["context"]["baseline_provenance"]["kind"] == "synthetic"


def test_recommendations_rerun_engines_preserve_scale_and_freeze_context(real_run):
    client, original, _ = real_run
    response = client.post(f"/api/v1/scenarios/integrated/{original['id']}/recommendations", json={})
    assert response.status_code == 201, response.text
    result = response.json()
    assert len(result["recommendations"]) == 3
    assert result["context"] == original["context"]
    assert result["variants"] == original["variants"]
    assert result["parent_id"] == original["id"]
    assert result["id"] != original["id"]
    assert result["input_sha256"] != original["input_sha256"]
    for candidate in result["recommendations"]:
        assert candidate["design"]["buildings"] == original["inputs"]["development"]["buildings"]
        assert candidate["scale_preserved"]
        assert candidate["predicted"]["traffic"]["artifacts"]["artifact_id"] != original["variants"]["development"]["traffic"]["artifacts"]["artifact_id"]
        assert candidate["predicted"]["drainage"]["balance_passed"]
    assert client.get(f"/api/v1/scenarios/integrated/{original['id']}").json() == original
    archive = client.get(f"/api/v1/scenarios/integrated/{result['id']}/artifacts")
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert json.loads(z.read("scenario.json"))["context"]["sha256"] == original["context"]["sha256"]
        assert any(name.endswith("drainage.inp") for name in z.namelist())


def test_budget_and_locked_actions_return_no_feasible_candidate(real_run):
    client, result, _ = real_run
    for constraints in ({"budget_vnd": 0}, {"allow_operations": False, "allow_storage": False, "allow_surface_changes": False}):
        response = client.post(f"/api/v1/scenarios/integrated/{result['id']}/recommendations", json=constraints)
        assert response.status_code == 201
        assert response.json()["recommendation_status"] == "no_feasible_candidate"


def test_failure_returns_503_and_no_fake_prediction(monkeypatch, tmp_path):
    monkeypatch.delenv("WAREHOUSE_PASSWORD", raising=False); monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SCENARIO_DATA_DIR", str(tmp_path))
    def fail(*args):
        raise solvers.SolverUnavailable("Engine unavailable")
    monkeypatch.setattr(solvers, "traffic", fail)
    response = TestClient(app).post("/api/v1/scenarios/integrated/predict", json=demo_payload())
    assert response.status_code == 503
    assert not list(tmp_path.glob("*.json"))


def test_synthetic_context_is_reproducible_without_timestamp(monkeypatch, tmp_path):
    monkeypatch.delenv("WAREHOUSE_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    request = IntegratedRequest(**demo_payload())
    a, b = build_context(request), build_context(request)
    assert a["sha256"] == b["sha256"]
    request.conditions.seed += 1
    assert build_context(request)["sha256"] != a["sha256"]


def test_hydraulic_regression_cannot_pass_only_screening_goals(real_run):
    _, result, _ = real_run
    before = result["variants"]["baseline"]
    changed = copy.deepcopy(result["variants"]["development"])
    changed["metrics"]["node_flooding_m3"] = before["metrics"]["node_flooding_m3"]*2+1
    assessment = engine.assess(before, changed, result["context"])
    assert not next(t for t in assessment["targets"] if t["metric"] == "node_flooding_m3")["met"]
    assert not assessment["targets_met"]


def test_minimum_paved_constraint_and_initial_storage_effect(real_run):
    client, result, _ = real_run
    response = client.post(f"/api/v1/scenarios/integrated/{result['id']}/recommendations", json={"minimum_paved_m2": 100000})
    assert response.status_code == 201 and not response.json()["recommendations"]
    design = Design(**demo_payload()["development"])
    with pytest.raises(ValueError, match="capacity"):
        Design(**{**design.model_dump(), "storage_initial_m3": 1})


def test_traffic_seed_reproducibility_and_stochastic_sample(real_run):
    _, result, _ = real_run
    design = Design(**result["inputs"]["development"])
    original = result["variants"]["development"]["traffic"]
    repeat = solvers.traffic(design, result["variants"]["development"]["demand"], result["context"])
    assert repeat["artifacts"]["files"]["routes.xml"]["sha256"] == original["artifacts"]["files"]["routes.xml"]["sha256"]
    assert repeat["mean_completed_delay_seconds"] == original["mean_completed_delay_seconds"]
    assert repeat["max_queue_length_m"] > 0
    context = copy.deepcopy(result["context"])
    context["seed"] += 1
    alternative = solvers.traffic(design, result["variants"]["development"]["demand"], context)
    assert alternative["planned_vehicles"] == original["planned_vehicles"]
    assert alternative["artifacts"]["files"]["routes.xml"]["sha256"] != original["artifacts"]["files"]["routes.xml"]["sha256"]
    assert alternative["planned_vehicles"] == alternative["completed_vehicles"]+alternative["unfinished_vehicles"]+alternative["undeparted_vehicles"]


def test_spare_power_uses_coincident_hour_not_difference_of_daily_peaks(real_run):
    _, result, _ = real_run
    before = copy.deepcopy(result['variants']['baseline'])
    after = copy.deepcopy(result['variants']['development'])
    before['demand']['hourly']['power_kw'] = [100]+[0]*23
    after['demand']['hourly']['power_kw'] = [100, 250]+[0]*22
    before['metrics']['power_peak_kw'] = 100
    after['metrics']['power_peak_kw'] = 250
    assessment = engine.assess(before, after, result['context'])
    power = next(t for t in assessment['targets'] if t['metric'] == 'power_peak_kw')
    assert power['comparison_value'] == 250
    assert not power['met']  # A difference-of-peaks shortcut would wrongly report 150 < 200.


def test_cached_snapshot_hash_matches_bytes_when_etl_publishes_concurrently(monkeypatch, tmp_path):
    monkeypatch.delenv("WAREHOUSE_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    layer = tmp_path/'layers'/'flood_history.geojson'
    layer.parent.mkdir()
    original = b'{"type":"FeatureCollection","features":[],"metadata":{"version":1}}'
    updated = b'{"type":"FeatureCollection","features":[],"metadata":{"version":2}}'
    layer.write_bytes(original)
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    real_read = Path.read_bytes
    def read_and_publish(path):
        raw = real_read(path)
        if path == layer:
            layer.write_bytes(updated)
        return raw
    monkeypatch.setattr(Path, 'read_bytes', read_and_publish)
    context = build_context(IntegratedRequest(**demo_payload()))
    snapshot = context['layers']['flood_history']
    assert snapshot['metadata']['version'] == 1
    assert snapshot['snapshot_sha256'] == hashlib.sha256(original).hexdigest()
