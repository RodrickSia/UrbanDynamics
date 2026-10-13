"""Native all-subsets and two commissioning orders through the live worker.

Writes inputs before enqueueing and job IDs immediately. Observation timeout
does not authorize replacing/restarting a live job.
"""
import argparse
from copy import deepcopy
from itertools import combinations
import io
import json
from pathlib import Path
import time
from uuid import uuid4
from xml.etree import ElementTree as ET
import zipfile

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--api", default="http://127.0.0.1:8007")
parser.add_argument("--output", type=Path, default=Path("test-results/planning-portfolio"))
parser.add_argument("--resume", action="store_true", help="Observe/reverify recorded jobs without enqueueing replacements")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


def physical(value):
    if isinstance(value, dict):
        return {k: physical(v) for k, v in value.items() if k != "artifacts"}
    if isinstance(value, list):
        return [physical(v) for v in value]
    return value


def check_close(actual, expected):
    assert abs(actual-expected) <= max(1e-7, abs(expected)*1e-9), (actual, expected)


def capacity_breaches(result):
    output = []
    for phase in result["phases"]:
        failures = [{"zone_id": zone["id"], "metric": check["metric"], "value": check["value"], "capacity": check["capacity"]}
                    for zone in phase["state"]["utility_zones"] for check in zone["checks"] if check["status"] == "exceeds_capacity"]
        assert bool(failures) == any(c["capacity"] is not None and c["value"] > c["capacity"]
                                     for z in phase["state"]["utility_zones"] for c in z["checks"] if c["status"] != "unknown")
        output.append({"phase_id": phase["id"], "active_project_ids": phase["state"]["active_project_ids"], "breaches": failures})
    return {"phases": output, "first_breach_phase": next((p["phase_id"] for p in output if p["breaches"]), None)}


started = time.perf_counter()
with httpx.Client(base_url=args.api+"/api/v1/planning", timeout=30) as client:
    deadline = time.monotonic()+30
    while True:
        try:
            response = client.get("/presets", timeout=2)
            if response.status_code == 200:
                break
        except httpx.TransportError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError("API not ready; inspect the existing server before restarting anything")
        time.sleep(.25)
    response = client.get("/presets")
    response.raise_for_status()
    base = response.json()["cumulative"]
    base["conditions"] = {"traffic_hours": [18], "seeds": [2026, 2027, 2028]}
    base["criteria"] = [{"metric": "school_unserved_students", "direction": "minimize"},
                        {"metric": "power_peak_kw", "direction": "minimize"}]
    base["options"] = [{"id": "".join(active), "title": "Active "+"+".join(active), "active_project_ids": list(active)}
                       for length in (1, 2, 3) for active in combinations(("A", "B", "C"), length)]
    results, records, networks = [], [], []
    for order, first in (("A-first", "A"), ("B-first", "B")):
        payload = deepcopy(base)
        payload["title"] = "All subsets; commissioning "+order
        payload["phases"] = [{"id": "phase_1", "sequence": 1, "title": "Commission "+first, "active_project_ids": [first]},
                             {"id": "phase_2", "sequence": 2, "title": "Commission A+B", "active_project_ids": ["A", "B"]},
                             {"id": "phase_3", "sequence": 3, "title": "Commission A+B+C", "active_project_ids": ["A", "B", "C"]}]
        (args.output/(order+"-input.json")).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ready = client.post("/studies/preflight", json=payload)
        ready.raise_for_status()
        assert ready.json()["unique_states"] == 8
        job_path = args.output/(order+"-job.json")
        if args.resume:
            recorded = json.loads(job_path.read_text(encoding="utf-8"))
            response = client.get("/jobs/"+recorded["id"])
            response.raise_for_status()
            job = response.json()
            response = client.get("/studies/"+job["study_id"])
            response.raise_for_status()
            study = response.json()
            assert study["context_hash"] == ready.json()["context_hash"]
            assert study["inputs"] == ready.json()["context"]["inputs"]
        else:
            response = client.post("/studies", json=payload)
            response.raise_for_status()
            study = response.json()
            request = {"mode": "native", "idempotency_key": "portfolio-"+uuid4().hex}
            response = client.post(f"/studies/{study['id']}/runs", json=request)
            response.raise_for_status()
            job = response.json()
        (args.output/(order+"-job.json")).write_text(json.dumps(job, indent=2), encoding="utf-8")
        print(json.dumps({"order": order, "job_id": job["id"]}), flush=True)
        if not args.resume:
            assert client.post(f"/studies/{study['id']}/runs", json=request).json()["id"] == job["id"]
        deadline = time.monotonic()+360
        while True:
            response = client.get("/jobs/"+job["id"])
            response.raise_for_status()
            current = response.json()
            if current["status"] not in ("queued", "running"):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Observation expired; inspect recorded existing job "+job["id"])
            time.sleep(.5)
        assert current["status"] == "succeeded", current
        response = client.get("/runs/"+current["result_id"])
        response.raise_for_status()
        result = response.json()
        assert result["unique_states_evaluated"] == 8 and all(result["validity"].values())
        assert result["context"]["sha256"] == ready.json()["context_hash"]
        options = {o["id"]: o["state"] for o in result["options"]}
        assert result["phases"][1]["state"] == options["AB"]
        assert result["phases"][2]["state"] == options["ABC"]
        previous = result["baseline"]
        for phase, marginal in zip(result["phases"], result["marginal_effects"]):
            for row in marginal["rows"]:
                a, b = phase["state"]["metrics"][row["metric"]], previous["metrics"][row["metric"]]
                if a is not None and b is not None:
                    check_close(row["delta"], a-b)
            previous = phase["state"]
        nonzero_native = []
        for interaction in result["interaction_effects"]:
            active = interaction["active_project_ids"]
            combined = options["".join(active)]
            for metric, value in interaction["metrics"].items():
                values = [combined["metrics"][metric], result["baseline"]["metrics"][metric]]+[options[p]["metrics"][metric] for p in active]
                if all(v is not None for v in values):
                    check_close(value, values[0]-values[1]-sum(v-values[1] for v in values[2:]))
            for metric in ("node_flooding_m3", "runoff_peak_m3_s"):
                if abs(interaction["metrics"][metric]) > 1e-7:
                    nonzero_native.append({"projects": active, "metric": metric, "interaction": interaction["metrics"][metric]})
        assert nonzero_native, "No demonstrated native interaction in this fixture"
        response = client.get("/runs/"+result["id"]+"/artifacts")
        response.raise_for_status()
        bundle = response.content
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            assert archive.testzip() is None
            assert json.loads(archive.read("result.json")) == result
            path = "solvers/"+result["network_artifacts"]["artifact_id"]+"/network.xml"
            networks.append(ET.tostring(ET.fromstring(archive.read(path))))
            assert {"comparison.csv", "normalized-comparison.csv", "baseline-ledger.csv", "source-manifest.json"} <= set(archive.namelist())
        (args.output/(order+"-result.json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
        (args.output/(order+".zip")).write_bytes(bundle)
        records.append({"order": order, "job_id": job["id"], "run_id": result["id"], "model_version": result["model_version"],
                        "unique_states": 8, "native_interactions": nonzero_native, "capacity": capacity_breaches(result)})
        assert records[-1]["capacity"]["first_breach_phase"] == "phase_3"
        results.append(result)
    assert results[0]["inputs"]["conditions"] == results[1]["inputs"]["conditions"]
    assert results[0]["inputs"]["projects"] == results[1]["inputs"]["projects"]
    assert networks[0] == networks[1]
    assert physical(results[0]["baseline"]) == physical(results[1]["baseline"])
    left = {o["id"]: physical(o["state"]) for o in results[0]["options"]}
    right = {o["id"]: physical(o["state"]) for o in results[1]["options"]}
    assert left == right
report = {"status": "passed", "seconds": time.perf_counter()-started, "runs": records,
          "reused_recorded_jobs": args.resume,
          "checks": ["eight native states", "two commissioning orders", "same physical network and per-subset results",
                     "marginal arithmetic", "nonzero native interaction", "phase state identity", "saved ZIP/CSV/manifest"]}
if not args.resume:
    report["checks"].append("idempotency")
(args.output/"portfolio-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
