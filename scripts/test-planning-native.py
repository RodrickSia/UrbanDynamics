"""Native pilot smoke: real SUMO/SWMM, shared baseline and phase equivalence."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root/"backend"), str(root/"etl")]
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.native import run_native

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mode", choices=["site_selection", "cumulative"], default="cumulative")
parser.add_argument("--output", type=Path, default=root/"test-results/planning-studies")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SIMULATION_WORK_DIR", str(root/".runtime/planning-demo/solvers"))
started = time.perf_counter()
def progress(value):
    if value["module"] != "solver":
        print(json.dumps(value), flush=True)
result = run_native(PlanningStudy(**demo_study(args.mode)), progress)
assert all(result["validity"].values()), result["validity"]
if args.mode == "cumulative":
    options = {o["id"]: o for o in result["options"]}
    assert options["ABC"]["state"] == result["phases"][2]["state"]
    assert options["AB"]["state"] == result["phases"][1]["state"]
path = args.output/f"{args.mode}-native.json"
path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
report = {"seconds": time.perf_counter()-started, "validity": result["validity"], "states": result["unique_states_evaluated"],
          "options": [{"id": o["id"], "flooding_m3": o["state"]["metrics"]["node_flooding_m3"],
                       "traffic": [{"hour": r["hour_local"], "planned": r["planned_vehicles"], "completed": r["completed_vehicles"],
                                    "delay": r["mean_completed_delay_seconds"], "queue": r["max_queue_length_m"]} for r in o["state"]["traffic"]["runs"]]} for o in result["options"]]}
(args.output/f"{args.mode}-native-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
