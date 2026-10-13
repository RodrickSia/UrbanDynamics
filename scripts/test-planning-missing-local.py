"""Verify unknown baseline propagation through the live API/worker and ZIP."""
import argparse
import csv
import io
import json
from pathlib import Path
import time
from uuid import uuid4
import zipfile

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--api", default="http://127.0.0.1:8007")
parser.add_argument("--output", type=Path, default=Path("test-results/planning-unknown-comparison"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
runs = []
with httpx.Client(base_url=args.api, timeout=30) as client:
    response = client.get("/api/v1/planning/presets")
    response.raise_for_status()
    payload = response.json()["cumulative"]
    payload["projects"] = payload["projects"][:2]
    payload["projects"][0]["baseline_occupancy"] = "unknown"
    payload["options"] = [o for o in payload["options"] if set(o["active_project_ids"]) <= {"A", "B"}]
    payload["phases"] = payload["phases"][:2]
    payload["conditions"] = {"traffic_hours": [18], "seeds": [2026]}
    payload["criteria"] = [{"metric": "power_peak_kw", "direction": "minimize"}]
    response = client.post("/api/v1/planning/studies", json=payload)
    response.raise_for_status()
    study = response.json()
    for mode in ("screening", "native"):
        response = client.post(f"/api/v1/planning/studies/{study['id']}/runs",
                               json={"mode": mode, "idempotency_key": "unknown-"+uuid4().hex})
        response.raise_for_status()
        job = response.json()
        (args.output/f"{mode}-job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
        print(json.dumps({"mode": mode, "job_id": job["id"]}), flush=True)
        deadline = time.monotonic()+360
        while True:
            response = client.get(f"/api/v1/planning/jobs/{job['id']}")
            response.raise_for_status()
            current = response.json()
            if current["status"] not in ("queued", "running"):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Observation timed out; inspect recorded job before retrying: "+job["id"])
            time.sleep(.5)
        assert current["status"] == "succeeded", current
        response = client.get(f"/api/v1/planning/runs/{current['result_id']}")
        response.raise_for_status()
        result = response.json()
        assert result["ranking"]["status"] == "insufficient_data"
        for option in result["options"]+result["phases"]:
            row = next(r for r in option["comparison"] if r["metric"] == "power_peak_kw")
            assert row["before"] is row["after"] is row["delta"] is None
            assert row["scenario_values"]["before"] is not None
            if mode == "native":
                assert all(r["delta"] is None and r["comparability"] == "insufficient_data" for r in option["traffic_comparison"])
        effect = next(e for e in result["interaction_effects"] if e["active_project_ids"] == ["A", "B"])
        assert effect["metrics"]["power_peak_kw"] is None
        assert effect["comparability_by_metric"]["power_peak_kw"] == "insufficient_data"
        assert effect["scenario_values"]["power_peak_kw"]["value"] is not None
        if mode == "native":
            assert effect["metrics"]["node_flooding_m3"] is not None
            assert all(result["validity"].values())
        response = client.get(f"/api/v1/planning/runs/{result['id']}/artifacts")
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.testzip() is None
            assert json.loads(archive.read("result.json")) == result
            rows = list(csv.DictReader(io.StringIO(archive.read("comparison.csv").decode("utf-8-sig"))))
            assert all(r["before"] == r["after"] == r["delta"] == "" for r in rows if r["metric"] == "power_peak_kw")
        (args.output/f"{mode}-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (args.output/f"{mode}.zip").write_bytes(response.content)
        runs.append({"mode": mode, "job_id": job["id"], "run_id": result["id"], "model_version": result["model_version"], "checks": "passed"})
report = {"status": "passed", "runs": runs,
          "checks": ["live API and separate worker", "unknown comparison null", "unknown interaction null", "assumptions separate", "ranking blocked", "ZIP/CSV missing values"]}
(args.output/"http-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
