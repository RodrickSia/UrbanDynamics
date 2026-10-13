"""Smoke test the live API with a separate durable worker process."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import zipfile

import httpx

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--api", default="http://127.0.0.1:8004")
parser.add_argument("--sqlite-path", type=Path, required=True)
parser.add_argument("--external-worker", action="store_true", help="Poll an existing worker instead of spawning a local one-shot worker")
parser.add_argument("--run-mode", choices=("screening", "native", "uncertainty"), default="screening")
parser.add_argument("--study-mode", choices=("both", "single_site", "site_selection", "cumulative"), default="both")
parser.add_argument("--hours", type=int, nargs="+")
parser.add_argument("--solver-root", type=Path, default=root/".runtime/planning-demo/solvers")
parser.add_argument("--output", type=Path, default=root/"test-results/planning-studies")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
environment = dict(os.environ, PLANNING_SQLITE_PATH=str(args.sqlite_path.resolve()),
                   SIMULATION_WORK_DIR=str(args.solver_root.resolve()), PYTHONPATH=str(root/"backend")+os.pathsep+str(root/"etl"))
started, reports = time.perf_counter(), []


def checked(response, status=200):
    if response.status_code != status:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
    return response


with httpx.Client(base_url=args.api, timeout=30) as client:
    deadline = time.monotonic()+30
    while True:
        try:
            response = client.get("/health", timeout=2)
            if response.status_code == 200:
                break
        except httpx.TransportError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError("API not ready; inspect the existing server before launching another")
        time.sleep(.25)
    presets = checked(client.get("/api/v1/planning/presets")).json()
    for mode in (("site_selection", "cumulative") if args.study_mode == "both" else (args.study_mode,)):
        payload = presets[mode]
        if args.hours:
            payload.setdefault("conditions", {})["traffic_hours"] = args.hours
        if args.run_mode == "uncertainty":
            payload["uncertainty"] = {"engine": "native", "seeds": [2026, 2027, 2028]}
        payload["criteria"] = [{"metric": "school_unserved_students", "direction": "minimize"},
                               {"metric": "power_peak_kw", "direction": "minimize"}]
        if args.run_mode in ("native", "uncertainty"):
            payload["criteria"].append({"metric": "background_completed_delay_seconds", "direction": "minimize"})
        ready = checked(client.post("/api/v1/planning/studies/preflight", json=payload)).json()
        study = checked(client.post("/api/v1/planning/studies", json=payload), 201).json()
        request = {"mode": args.run_mode, "idempotency_key": "smoke-"+uuid4().hex}
        job = checked(client.post(f"/api/v1/planning/studies/{study['id']}/runs", json=request), 202).json()
        duplicate = checked(client.post(f"/api/v1/planning/studies/{study['id']}/runs", json=request), 202).json()
        assert duplicate["id"] == job["id"]
        if args.external_worker:
            deadline = time.monotonic()+360
            while True:
                current = checked(client.get(f"/api/v1/planning/jobs/{job['id']}")).json()
                if current["status"] not in ("queued", "running"):
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Observation timed out; job may still run. Inspect this job ID before retrying: "+job["id"])
                time.sleep(.5)
        else:
            worker = subprocess.run([sys.executable, str(root/"scripts/planning-worker.py"), "--once"],
                                    env=environment, capture_output=True, text=True, timeout=360)
            if worker.returncode:
                raise RuntimeError(f"Worker failed: {worker.stderr[-2000:]}")
        final = checked(client.get(f"/api/v1/planning/jobs/{job['id']}")).json()
        assert final["status"] == "succeeded", final
        result = checked(client.get(f"/api/v1/planning/runs/{final['result_id']}")).json()
        if mode == "single_site" and args.run_mode != "uncertainty":
            assert result["execution_path"] == "single_site_shared_context"
        assert result.get("analysis_request_context_hash", result["context"]["sha256"]) == ready["context_hash"]
        assert checked(client.get(f"/api/v1/planning/studies/{study['id']}")).json() == study
        bundle = checked(client.get(f"/api/v1/planning/runs/{result['id']}/artifacts")).content
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            assert archive.testzip() is None
            assert json.loads(archive.read("result.json")) == result
            assert json.loads(archive.read("source-manifest.json")) == result["context"]["source_manifest"]
            if args.run_mode in ("native", "uncertainty"):
                assert any(name.endswith("network.xml") for name in archive.namelist())
                assert any(name.endswith("drainage.inp") for name in archive.namelist())
        assert result["ranking"]["status"] == "scenario_only"
        mapped = checked(client.get(f"/api/v1/planning/runs/{result['id']}/map", params={"option_id": result["options"][0]["id"], "name": "school"})).json()
        assert mapped["coordinate_reference"] == "EPSG:4326"
        assert mapped["source_manifest_id"] == result["context"]["snapshot_manifest_id"]
        assert mapped["module_coverage"]["observed_coverage"] is False
        assert all(f["properties"]["study_id"] == study["id"] for f in mapped["features"])
        for option in result["options"]:
            assert all(option["state"]["school_services"]["validity"].values())
            if args.run_mode in ("native", "uncertainty"):
                assert all(result["validity"].values())
                for catchment in option["state"]["drainage"]["catchments"]:
                    assert catchment["timeseries"]["nodes"] and catchment["timeseries"]["links"]
        prefix = f"{mode}-{args.run_mode}"
        (args.output/f"{prefix}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output/f"{prefix}.zip").write_bytes(bundle)
        reports.append({"mode": mode, "study_id": study["id"], "job_id": job["id"], "run_id": result["id"],
                        "context_hash": ready["context_hash"], "model_version": result["model_version"],
                        "source_manifest_id": result["context"]["snapshot_manifest_id"], "unique_states": result["unique_states_evaluated"],
                        "options": [{"id": option["id"], "power_peak_kw": option["state"]["metrics"]["power_peak_kw"],
                                     "zone_checks": option["state"]["utility_zones"][0]["checks"]} for option in result["options"]],
                        "native": args.run_mode in ("native", "uncertainty"), "zip_bytes": len(bundle), "checks": "passed"})
report = {"status": "passed", "seconds": time.perf_counter()-started, "stages_verified": ["preflight", "durable_queue", "separate_worker", args.run_mode, "school_allocation", "shadow_union", "criteria", "read", "immutable_study", "idempotency", "zip"],
          "not_verified_by_this_command": (["uncertainty"] if args.run_mode != "uncertainty" else [])+["demo_UI", "job_recovery", "postgres_verification"], "runs": reports}
(args.output/f"http-{args.run_mode}-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
