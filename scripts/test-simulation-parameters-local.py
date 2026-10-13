"""Verify the running API's demand catalog and saved OAT/SUMO analyses."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import time
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8003")
    parser.add_argument("--snapshot-id")
    args = parser.parse_args()
    payload = json.loads((ROOT / "docs/samples/simulation-map-context.json").read_text(encoding="utf-8"))
    if args.snapshot_id:
        payload.update(data_mode="snapshot_required", snapshot_id=args.snapshot_id)
    started = time.perf_counter()
    with httpx.Client(base_url=args.base_url, timeout=300) as client:
        def checked(response, status=200):
            if response.status_code != status:
                raise RuntimeError(f"API {response.status_code}: {response.text[:500]}")
            return response

        catalog = checked(client.get("/api/v1/scenarios/integrated/parameters")).json()
        office = catalog["parameters"]["uses.office.energy_kwh_m2_day"]
        assert abs(office["value"] * 365 - 116.4) < 1e-9
        assert office["data_year"] == 2015 and office["needs_local_calibration"]
        assert catalog["parameters"]["return_fraction"]["numeric_source"] is None
        assert catalog["parameters"]["uses.residential.water_l_person_day"]["numeric_source"] is None
        demo = checked(client.get("/api/v1/scenarios/integrated/parameters", params={"profile": "demo"})).json()
        assert demo["parameters"]["uses.office.energy_kwh_m2_day"]["value"] == .14
        print("Catalog: annual office EUI conversion and assumption labels verified", flush=True)
        context = checked(client.post("/api/v1/scenarios/integrated/context", json=payload)).json()
        assert context["demand_parameter_catalog"]["profile"] == "reviewed"
        source = checked(client.post("/api/v1/scenarios/integrated/predict", json=payload), 201).json()
        assert source["model_version"] == "integrated-building-1.4"
        assert all(all(v["validity"].values()) for v in source["variants"].values())
        print("Prediction:", source["id"], source["context"]["traffic_network_kind"], flush=True)
        demand = checked(client.post(f"/api/v1/scenarios/integrated/{source['id']}/sensitivity", json={
            "parameter_ids": ["uses.residential.water_l_person_day", "return_fraction", "uses.residential.energy_kwh_m2_day"]}), 201).json()
        assert len(demand["sensitivity"]["cases"]) == 6
        assert not demand["sensitivity"]["native_engines_recomputed"]
        assert demand["context"] == source["context"]
        assert checked(client.get(f"/api/v1/scenarios/integrated/{demand['id']}")).json() == demand
        print("Demand sensitivity: six cases saved and read back", flush=True)
        traffic = checked(client.post(f"/api/v1/scenarios/integrated/{source['id']}/sensitivity", json={
            "mode": "native_traffic", "parameter_ids": ["uses.residential.resident_trips_day"]}), 201).json()
        assert traffic["context"] == source["context"]
        assert checked(client.get(f"/api/v1/scenarios/integrated/{traffic['id']}")).json() == traffic
        expected_artifacts, traffic_cases = [], []
        for case in traffic["sensitivity"]["cases"]:
            case_report = {"level": case["level"], "person_trips_per_resident_day": case["value"], "variants": {}}
            for name, state in case["variants"].items():
                result = state["traffic"]
                assert all(state["validity"].values())
                assert result["planned_vehicles"] == result["completed_vehicles"] + result["unfinished_vehicles"] + result["undeparted_vehicles"]
                assert result["peak_hour_local"] == source["context"]["traffic_peak_hour"]
                expected_artifacts.append(result["artifacts"]["artifact_id"])
                case_report["variants"][name] = {key: result[key] for key in (
                    "planned_vehicles", "completed_vehicles", "unfinished_vehicles", "undeparted_vehicles",
                    "mean_completed_delay_seconds", "max_queue_length_m", "peak_hour_local")}
            traffic_cases.append(case_report)
        assert len(traffic_cases) == 2
        archive = checked(client.get(f"/api/v1/scenarios/integrated/{traffic['id']}/artifacts"))
        with zipfile.ZipFile(BytesIO(archive.content)) as bundle:
            names = bundle.namelist()
            assert bundle.testzip() is None and len(names) == len(set(names))
            assert all(any(name.startswith(identifier + "/") for name in names) for identifier in expected_artifacts)
            assert json.loads(bundle.read("scenario.json")) == traffic
        assert checked(client.get(f"/api/v1/scenarios/integrated/{source['id']}")).json() == source
        print("Native traffic sensitivity: four SUMO runs, immutable parent and ZIP verified", flush=True)
    report = {"passed": True, "elapsed_seconds": round(time.perf_counter() - started, 2),
              "model_version": source["model_version"], "library_version": catalog["library_version"],
              "run_id": source["id"], "demand_analysis_id": demand["id"], "traffic_analysis_id": traffic["id"],
              "snapshot_id": source["context"]["data_inventory"].get("snapshot_id"),
              "traffic_network_kind": source["context"]["traffic_network_kind"],
              "catalog_count": len(catalog["parameters"]),
              "source_backed_default_count": sum(bool(p["numeric_source"]) for p in catalog["parameters"].values()),
              "demand_case_count": len(demand["sensitivity"]["cases"]), "traffic_case_count": len(traffic_cases),
              "parent_unchanged": True, "storage_roundtrip": True, "native_validity_passed": True,
              "artifact_zip_no_duplicates": True, "artifacts_bytes": len(archive.content),
              "reference_demand": demand["sensitivity"]["reference"]["rows"],
              "demand_stability": demand["sensitivity"]["stability"],
              "demand_target_stability": demand["sensitivity"]["target_stability"], "traffic_cases": traffic_cases,
              "note": "Engineering checks, not observed impact accuracy validation. Client map fixture is synthetic; snapshot topology/surfaces/population are sourced, other unresolved assumptions remain labeled."}
    output = ROOT / "test-results"
    output.mkdir(exist_ok=True)
    for name, document in (("simulation-parameters-local-report.json", report), ("parameters-demo.json", source),
                           ("parameters-demand-sensitivity.json", demand), ("parameters-traffic-sensitivity.json", traffic)):
        (output / name).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "parameters-traffic-sensitivity.zip").write_bytes(archive.content)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
