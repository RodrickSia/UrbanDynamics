"""Verify actual installed team snapshot -> selected parcel -> native job/ZIP."""
import argparse
import io
import json
from pathlib import Path
import time
from uuid import uuid4
import zipfile

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--api", default="http://127.0.0.1:8007")
parser.add_argument("--output", type=Path, default=Path("test-results/planning-system-demo"))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
with httpx.Client(base_url=args.api+"/api/v1/planning", timeout=60) as c:
    snapshots = c.get("/demo/system/snapshots"); snapshots.raise_for_status()
    snapshot = max(snapshots.json()["snapshots"], key=lambda s: s["captured_at"])
    response = c.get("/demo/system/snapshots/"+snapshot["id"]+"/parcels"); response.raise_for_status()
    features = response.json()["features"]
    selected = features[0]
    request = {"snapshot_id": snapshot["id"], "parcel_ids": [str(selected["id"])], "conditions": {"traffic_hours": [18], "seeds": [2026, 2027, 2028]}}
    response = c.post("/demo/system/prepare", json=request); response.raise_for_status()
    payload = response.json()["study"]
    assert payload["projects"][0]["site"] == selected["geometry"]
    response = c.post("/studies/preflight", json=payload); response.raise_for_status()
    ready = response.json()
    assert ready["context"]["source_kind"] == "mixed_demo"
    assert ready["context"]["system_background"]["snapshot_id"] == snapshot["id"]
    assert ready["context"]["resolved_background"]["normalization"]["status"] == "inclusive_population_prior_unresolved"
    response = c.post("/studies", json=payload); response.raise_for_status()
    study = response.json()
    response = c.post(f"/studies/{study['id']}/runs", json={"mode": "native", "idempotency_key": "system-live-"+uuid4().hex}); response.raise_for_status()
    job = response.json()
    (args.output/"job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
    print(json.dumps({"job_id": job["id"], "parcel_id": selected["id"]}), flush=True)
    deadline = time.monotonic()+360
    while True:
        response = c.get("/jobs/"+job["id"]); response.raise_for_status()
        final = response.json()
        if final["status"] not in ("queued", "running"):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Inspect existing recorded job before retrying: "+job["id"])
        time.sleep(.5)
    assert final["status"] == "succeeded", final
    response = c.get("/runs/"+final["result_id"]); response.raise_for_status()
    result = response.json()
    assert all(result["validity"].values())
    assert result["context"]["sha256"] == ready["context_hash"]
    assert result["context"]["system_background"]["parcel_bindings"] == {"P1": str(selected["id"])}
    row = next(r for r in result["options"][0]["comparison"] if r["metric"] == "power_peak_kw")
    assert row["delta"] is None and row["comparability"] == "insufficient_data"
    response = c.get(f"/runs/{result['id']}/map", params={"name": "parcels", "option_id": "P1_only"}); response.raise_for_status()
    collection = response.json()
    assert collection["features"][0]["geometry"] == selected["geometry"]
    assert collection["source_kind"] == "mixed_demo"
    response = c.get(f"/runs/{result['id']}/artifacts"); response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read("result.json")) == result
    (args.output/"native.zip").write_bytes(response.content)
    (args.output/"native-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    report = {"status": "passed", "snapshot_id": snapshot["id"], "captured_at": snapshot["captured_at"],
              "eligible_parcels": len(features), "parcel_id": selected["id"], "parcel_area_m2": selected["demo_area_m2"],
              "population_prior": payload["background_residents"], "job_id": job["id"], "run_id": result["id"],
              "model_version": result["model_version"], "checks": ["actual system snapshot", "exact parcel geometry", "frozen sourced context", "unknown occupancy/capacity retained", "native SUMO/SWMM", "GeoJSON and ZIP"]}
    (args.output/"http-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
