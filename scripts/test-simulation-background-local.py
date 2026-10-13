"""Exercise published pilot data, API, native engines and immutable reruns locally."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"backend"), str(ROOT/"etl")]
from fastapi.testclient import TestClient
from app.main import app
from app.routers.integrated_scenarios import demo_payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id")
    parser.add_argument("--skip-recommendations", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("SCENARIO_DATA_DIR", str(ROOT/".runtime"/"background-smoke"/"runs"))
    os.environ.setdefault("SIMULATION_WORK_DIR", str(ROOT/".runtime"/"background-smoke"/"solvers"))
    started = time.perf_counter()
    payload = demo_payload()
    payload["data_mode"] = "snapshot_required"
    if args.snapshot_id:
        payload["snapshot_id"] = args.snapshot_id
    client = TestClient(app)
    def checked(response, status=200):
        if response.status_code != status:
            raise RuntimeError(f"API {response.status_code}: {response.text[:500]}")
        return response
    context = checked(client.post("/api/v1/scenarios/integrated/context", json=payload)).json()
    print("Preflight:", context["traffic_network_kind"], context["background_population"], "people", len(context["services"]), "services", flush=True)
    result = checked(client.post("/api/v1/scenarios/integrated/predict", json=payload), 201).json()
    print("Prediction:", result["id"], flush=True)
    assert checked(client.get(f"/api/v1/scenarios/integrated/{result['id']}")).json() == result
    for state in result["variants"].values():
        assert all(state["validity"].values())
        assert state["traffic"]["kind"] == "mixed_osm_and_estimates"
    before, after = (result["variants"][name]["traffic"] for name in ("baseline", "development"))
    assert before["peak_hour_local"] == after["peak_hour_local"]
    snapshot_hash = result["context"]["sha256"]
    recommendations = None
    if not args.skip_recommendations:
        recommendations = checked(client.post(f"/api/v1/scenarios/integrated/{result['id']}/recommendations", json={}), 201).json()
        assert recommendations["context"]["sha256"] == snapshot_hash
        for candidate in recommendations["recommendations"]:
            assert candidate["design"]["buildings"] == result["inputs"]["development"]["buildings"]
            assert candidate["predicted"]["traffic"]["peak_hour_local"] == after["peak_hour_local"]
            assert all(candidate["predicted"]["validity"].values())
        print("Recommendations:", len(recommendations["recommendations"]), recommendations["recommendation_status"], flush=True)
    archive = checked(client.get(f"/api/v1/scenarios/integrated/{result['id']}/artifacts"))
    report = {"passed": True, "elapsed_seconds": round(time.perf_counter()-started, 2), "run_id": result["id"],
              "model_version": result["model_version"], "snapshot_id": context["data_inventory"]["snapshot_id"],
              "population": context["background_population"], "population_year": context["population_provenance"]["source"]["year"],
              "services": len(context["services"]), "context_frozen": True, "storage_roundtrip": True,
              "artifacts_bytes": len(archive.content), "recommendations": len(recommendations["recommendations"]) if recommendations else None,
              "traffic": {name: {key: result["variants"][name]["traffic"][key] for key in
                         ("planned_vehicles", "completed_vehicles", "unfinished_vehicles", "undeparted_vehicles", "mean_completed_delay_seconds", "max_queue_length_m", "peak_hour_local")}
                         for name in ("baseline", "development")},
              "network": after["network_provenance"], "coverage": context["data_inventory"]["coverage"],
              "note": "Solver/API checks, not validation against local observations. Existing occupancy, OD, capacities and drainage remain assumptions."}
    directory = ROOT/"test-results"
    directory.mkdir(exist_ok=True)
    for name, data in (("background-demo.json", result), ("simulation-background-local-report.json", report)):
        (directory/name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if recommendations:
        (directory/"background-recommendations.json").write_text(json.dumps(recommendations, ensure_ascii=False), encoding="utf-8")
    (directory/"background-demo.zip").write_bytes(archive.content)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
