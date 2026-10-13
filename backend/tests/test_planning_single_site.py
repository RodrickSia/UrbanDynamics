from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.simulation.integrated.engine import predict_shared_study
from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.engine import run_screening
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.native import run_native
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning import store
from app.services.simulation.planning.jobs import process_one


def payload():
    data = demo_study()
    data["projects"] = data["projects"][:1]
    data["options"] = data["options"][:1]
    data["conditions"] = {"traffic_hours": [18], "seeds": [2026, 2027]}
    return data


def physics(value):
    if isinstance(value, dict):
        return {k: physics(v) for k, v in value.items() if k not in ("artifacts", "network_artifacts", "execution_path")}
    if isinstance(value, list):
        return [physics(v) for v in value]
    return value


def test_real_native_single_site_equals_portfolio_on_frozen_context(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path / "solvers"))
    study = PlanningStudy(**payload())
    context = build_context(study)
    immutable = deepcopy(context)
    single = predict_shared_study(study, frozen_context=context)
    portfolio = run_native(study)
    assert context == immutable
    assert single["context"] == portfolio["context"] == immutable
    assert single["execution_path"] == "single_site_shared_context"
    for key in ("baseline", "options", "phases", "standalone_states", "marginal_effects",
                "interaction_effects", "normalization", "ranking", "validity"):
        if key in single or key in portfolio:
            assert physics(single[key]) == physics(portfolio[key]), key
    assert all(single["validity"].values())
    # Independent solver executions, never a reused portfolio output.
    assert single["network_artifacts"]["artifact_id"] != portfolio["network_artifacts"]["artifact_id"]
    # netconvert comments include timestamp and absolute output directory;
    # compare all parsed topology/geometry/attribute values, not those comments.
    root = tmp_path / "solvers"
    single_network = ET.parse(root / single["network_artifacts"]["artifact_id"] / "network.xml")
    portfolio_network = ET.parse(root / portfolio["network_artifacts"]["artifact_id"] / "network.xml")
    assert ET.tostring(single_network.getroot()) == ET.tostring(portfolio_network.getroot())
    assert single["baseline"]["traffic"]["runs"][0]["artifacts"]["artifact_id"] != portfolio["baseline"]["traffic"]["runs"][0]["artifacts"]["artifact_id"]


@pytest.mark.parametrize("baseline_only", [False, True])
def test_screening_equal_and_rejects_stale_context(baseline_only):
    data = payload()
    if baseline_only:
        data["options"][0]["active_project_ids"] = []
        data["mode"] = "cumulative"
        data["comparison_policy"] = "declared_programs"
        data["program_targets"] = None
    study = PlanningStudy(**data)
    context = build_context(study)
    assert physics(predict_shared_study(study, "screening", frozen_context=context)) == physics(run_screening(study))
    changed = deepcopy(context)
    changed["library"]["rainfall_mm"] += 1
    with pytest.raises(ValueError, match="does not match"):
        predict_shared_study(study, "screening", frozen_context=changed)
    with pytest.raises(ValueError, match="exactly one"):
        predict_shared_study(PlanningStudy(**demo_study()), "screening")


def test_single_site_api_job_uses_integrated_shared_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path / "studies.sqlite"))
    with TestClient(app) as client:
        assert client.post("/api/v1/planning/single-site/studies", json=demo_study()).status_code == 422
        created = client.post("/api/v1/planning/single-site/studies", json=payload())
        assert created.status_code == 201
        job = client.post(f"/api/v1/planning/studies/{created.json()['id']}/runs",
                          json={"mode": "screening", "idempotency_key": "single-site-screening"})
        assert job.status_code == 202
        done = process_one()
        assert done["status"] == "succeeded"
        result = store.load_document(done["result_id"], "run")
        assert result["execution_path"] == "single_site_shared_context"
        assert result["context"]["sha256"] == created.json()["context_hash"]
        assert client.get(f"/api/v1/planning/runs/{done['result_id']}/map",
                          params={"option_id": "A_only", "name": "school"}).status_code == 200
