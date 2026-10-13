"""Read-only verification of chunked series against saved native solver data."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--api", default="http://127.0.0.1:8007")
parser.add_argument("--evidence", type=Path, default=Path("test-results/planning-single-site"))
args = parser.parse_args()
checks = []
with httpx.Client(base_url=args.api+"/api/v1/planning", timeout=30) as client:
    for report_name in ("http-native-report.json", "http-uncertainty-report.json"):
        report = json.loads((args.evidence/report_name).read_text(encoding="utf-8"))
        for run in report["runs"]:
            response = client.get("/runs/"+run["run_id"])
            response.raise_for_status()
            document = response.json()
            before = deepcopy(document)
            cases = document.get("assumption_cases", [{"id": None, "result": document}])
            url = "/runs/"+run["run_id"]+"/timeseries"
            for case in cases:
                body = case["result"]
                option = body["phases"][-1] if body["phases"] else body["options"][0]
                state = option["state"]
                for catchment in state["drainage"]["catchments"]:
                    cid = catchment["catchment_id"]
                    for name, group in (("drainage", "nodes"), ("drainage_links", "links"), ("runoff", None)):
                        object_id = next(iter(catchment["timeseries"][group])) if group else cid
                        params = {"option_id": option["id"], "name": name, "object_id": object_id, "catchment_id": cid, "limit": 37}
                        if case["id"] is not None:
                            params["case_id"] = case["id"]
                        offset, samples = 0, []
                        while offset is not None:
                            response = client.get(url, params={**params, "offset": offset})
                            response.raise_for_status()
                            chunk = response.json()
                            assert chunk["context_hash"] == body["context"]["sha256"]
                            assert chunk["assumption_case_id"] == case["id"]
                            assert chunk["source_ids"] and chunk["units"] and len(chunk["samples"]) <= 37
                            samples.extend(chunk["samples"])
                            offset = chunk["pagination"]["next_offset"]
                        source = catchment["timeseries"][group][object_id] if group else {"runoff_m3_s": catchment["timeseries"]["runoff_m3_s"]}
                        assert [s["minute"] for s in samples] == catchment["timeseries"]["minute"]
                        for metric, values in source.items():
                            assert [s["values"][metric] for s in samples] == values
                        assert client.get(url, params={**params, "offset": len(samples)}).json()["samples"] == []
                        for invalid in ({"limit": 301}, {"object_id": "missing-object"}, {"offset": len(samples)+1}, {"seed": 2026}):
                            assert client.get(url, params={**params, **invalid}).status_code == 422
                traffic = state["traffic"]["runs"][-1]
                road_id = body["spatial_artifacts"]["roads"]["features"][0]["properties"]["edge_id"]
                params = {"option_id": option["id"], "name": "roads", "object_id": road_id,
                          "hour": traffic["hour_local"], "seed": traffic["seed"], "limit": 300}
                if case["id"] is not None:
                    params["case_id"] = case["id"]
                response = client.get(url, params=params)
                response.raise_for_status()
                chunk = response.json()
                assert len(chunk["samples"]) == len(traffic["edge_intervals"])
                for sample, interval in zip(chunk["samples"], traffic["edge_intervals"]):
                    edge = next((e for e in interval["edges"] if e["edge_id"] == road_id), None)
                    assert sample["values"]["speed"] == (edge.get("speed") if edge else None)
                checks.append({"run_id": run["run_id"], "mode": run["mode"], "case_id": case["id"],
                               "model_version": body["model_version"], "status": "passed"})
            assert client.get("/runs/"+run["run_id"]).json() == before
result = {"status": "passed", "checks": checks,
          "scope": "Read-only native/uncertainty object series, pagination, case/context, units/sources, invalid selectors and saved-run immutability"}
(args.evidence/"http-series-report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
