"""Run inside the backend image to check Linux worker/native/cancel/cache."""
import json
from pathlib import Path
import subprocess
import sys
import time

from app.services.simulation.planning import store, identity
from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.jobs import process_one, Cancelled
from app.services.simulation.planning.runner import execute
from app.services.simulation.integrated.solvers import workdir, SolverUnavailable

started = time.perf_counter()
payload = demo_study()
payload["projects"], payload["options"] = payload["projects"][:1], payload["options"][:1]
payload["conditions"] = {"traffic_hours": [18]}
context = build_context(PlanningStudy(**payload))
saved = store.save_study(context["inputs"], context["sha256"])
store.enqueue(saved["id"], "native", "linux-native-first")
first = process_one()
assert first["status"] == "succeeded", first
result = store.load_document(first["result_id"], "run")
assert all(result["validity"].values())
assert result["execution_path"] == "single_site_shared_context"
assert result["context"]["source_manifest"]["sha256"]
assert result["options"][0]["normalized_comparison"]
assert result["options"][0]["state"]["traffic"]["runs"][0]["queue_intervals"]
assert result["options"][0]["state"]["drainage"]["catchments"][0]["link_map"]["features"]
assert all(row["source_manifest_id"] == result["context"]["snapshot_manifest_id"] for option in result["options"] for row in option["comparison"]+option["traffic_comparison"]+option["drainage_comparison"])
assert result["child_cache"]["computed"] == 5
store.enqueue(saved["id"], "native", "linux-native-cached")
second = process_one()
cached = store.load_document(second["result_id"], "run")
assert cached["child_cache"]["hits"] == 5 and cached["child_cache"]["computed"] == 0
assert result["baseline"] == cached["baseline"] and result["options"] == cached["options"]
seen = []
directory = workdir("linux-interrupt")
command = [sys.executable, "-c", "import time;time.sleep(30)"]
try:
    execute(command, directory, lambda p: seen.append(p["child_identity"]), timeout=.1)
    raise AssertionError("Timeout did not happen")
except SolverUnavailable:
    assert identity.state(seen[-1]) == "stopped"
def cancel(progress):
    seen.append(progress["child_identity"])
    raise Cancelled()
try:
    execute(command, directory, cancel)
    raise AssertionError("Cancellation did not happen")
except Cancelled:
    assert identity.state(seen[-1]) == "stopped"
worker = subprocess.run([sys.executable, "-m", "app.services.simulation.planning.worker", "--once"], capture_output=True, timeout=30)
assert worker.returncode == 0
print(json.dumps({"status": "passed", "seconds": time.perf_counter()-started,
                  "model_version": result["model_version"], "source_manifest_id": result["context"]["snapshot_manifest_id"],
                  "checks": ["Linux actual SUMO/SWMM", "normalized program impacts", "spatial queues and SWMM links", "frozen source manifest", "durable child cache", "cancel/timeout process shutdown", "Docker worker entrypoint"],
                  "first_computed": 5, "second_cache_hits": 5, "second_computed": 0}, indent=2))
