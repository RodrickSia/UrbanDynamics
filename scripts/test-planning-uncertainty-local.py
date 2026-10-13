"""Run actual native assumption cases with a paired three-seed suite."""
import argparse
import json
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root/"backend"), str(root/"etl")]
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.uncertainty import run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=root/"test-results/planning-studies")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
payload = demo_study()
payload["conditions"] = {"traffic_hours": [18]}
payload["criteria"] = [{"metric": "background_completed_delay_seconds", "direction": "minimize", "weight": 1},
                       {"metric": "school_unserved_students", "direction": "minimize", "weight": 1}]
payload["uncertainty"] = {"engine": "native", "seeds": [2026, 2027, 2028]}
started = time.perf_counter()
result = run(PlanningStudy(**payload))
for case in result["assumption_cases"]:
    assert all(case["result"]["validity"].values())
    assert case["result"]["seed_analysis"]["status"] == "sampled"
    assert case["result"]["seed_analysis"]["seed_suite"] == [2026, 2027, 2028]
    for option in case["result"]["options"]:
        assert len(option["state"]["traffic"]["runs"]) == 3
    assert all(p["status"] == "sampled" for p in case["result"]["seed_analysis"]["option_pairs"])
    manifest_id = case["result"]["context"]["snapshot_manifest_id"]
    assert all(row["source_manifest_id"] == manifest_id for option in case["result"]["options"] for row in option["comparison"]+option["traffic_comparison"]+option["drainage_comparison"])
assert all(c["result"]["inputs"]["projects"] == result["inputs"]["projects"] for c in result["assumption_cases"])
(args.output/"uncertainty-native.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
report = {"status": "passed", "seconds": time.perf_counter()-started,
          "model_version": result["model_version"],
          "case_source_manifest_ids": {case["id"]: case["result"]["context"]["snapshot_manifest_id"] for case in result["assumption_cases"]},
          "case_ids": result["uncertainty_analysis"]["case_ids"], "sumo_runs": 36, "swmm_runs": 12,
          "ranking_stability": result["uncertainty_analysis"]["ranking_stability_across_cases"],
          "overall_ranking_assessment": result["uncertainty_analysis"]["overall_ranking_assessment"],
          "seed_rankings": [{"case_id": c["id"], "stability": c["result"]["seed_analysis"]["ranking_stability"]} for c in result["assumption_cases"]],
          "request_context_hash": result["analysis_request_context_hash"], "reference_context_hash": result["context"]["sha256"]}
(args.output/"uncertainty-native-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
