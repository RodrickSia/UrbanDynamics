"""Test the running local API using labeled map fixtures and optional real snapshot."""
import argparse
import json
from pathlib import Path
import time
import zipfile
from io import BytesIO

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8003")
    parser.add_argument("--snapshot-id")
    args = parser.parse_args()
    payload = json.loads((ROOT/"docs/samples/simulation-map-context.json").read_text(encoding="utf-8"))
    if args.snapshot_id:
        payload.update(data_mode="snapshot_required", snapshot_id=args.snapshot_id)
    started = time.perf_counter()
    with httpx.Client(base_url=args.base_url, timeout=300) as client:
        def checked(response, status=200):
            if response.status_code != status:
                raise RuntimeError(f"API {response.status_code}: {response.text[:500]}")
            return response
        schema = checked(client.get("/api/v1/openapi.json")).json()
        assert "map_context" in schema["components"]["schemas"]["IntegratedRequest"]["properties"]
        context = checked(client.post("/api/v1/scenarios/integrated/context", json=payload)).json()
        print("Preflight:", context["traffic_network_kind"], "network,", len(context["surrounding_buildings"]["features"]), "surrounding parts", flush=True)
        result = checked(client.post("/api/v1/scenarios/integrated/predict", json=payload), 201).json()
        print("Prediction:", result["id"], flush=True)
        assert result["model_version"] == "integrated-building-1.4"
        assert checked(client.get(f"/api/v1/scenarios/integrated/{result['id']}")).json() == result
        frozen = result["context"]["surrounding_buildings"]
        assert frozen["features"]
        for state in result["variants"].values():
            assert all(state["validity"].values())
            assert state["shadow"]["surrounding_buildings"] == frozen
        recommendations = checked(client.post(f"/api/v1/scenarios/integrated/{result['id']}/recommendations", json={}), 201).json()
        assert recommendations["context"] == result["context"]
        assert recommendations["recommendations"]
        for candidate in recommendations["recommendations"]:
            assert candidate["predicted"]["shadow"]["surrounding_buildings"] == frozen
            assert all(candidate["predicted"]["validity"].values())
        archive = checked(client.get(f"/api/v1/scenarios/integrated/{recommendations['id']}/artifacts"))
        with zipfile.ZipFile(BytesIO(archive.content)) as bundle:
            assert bundle.testzip() is None
            assert json.loads(bundle.read("scenario.json"))["context"] == result["context"]
    report = {"passed": True, "elapsed_seconds": round(time.perf_counter()-started, 2),
              "model_version": result["model_version"], "run_id": result["id"], "recommendation_run_id": recommendations["id"],
              "map_source": "TEST_FIXTURE_NOT_REAL_GOONG", "snapshot_id": result["context"]["data_inventory"].get("snapshot_id"),
              "traffic_network_kind": result["context"]["traffic_network_kind"],
              "baseline_buildings": len(result["context"]["baseline"]["buildings"]), "surrounding_parts": len(frozen["features"]),
              "context_frozen": True, "storage_roundtrip": True, "native_validity_passed": True,
              "recommendations": len(recommendations["recommendations"]), "artifacts_bytes": len(archive.content),
              "shadow": {name: {key: result["variants"][name]["shadow"][key] for key in
                         ("engine", "mean_outdoor_shaded_percent", "surrounding_building_count")} for name in result["variants"]},
              "note": "API and engine checks only. Map buildings are synthetic fixtures; snapshot sources, when supplied, are real downloaded context. No observed impact accuracy validation."}
    output = ROOT/"test-results"
    output.mkdir(exist_ok=True)
    for name, document in (("simulation-map-context-local-report.json", report), ("map-context-demo.json", result), ("map-context-recommendations.json", recommendations)):
        (output/name).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    (output/"map-context-demo.zip").write_bytes(archive.content)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
