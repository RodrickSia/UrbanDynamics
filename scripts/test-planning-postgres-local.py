"""Isolated PostgreSQL/PostGIS storage check with actual native child caching.

Creates and removes only its own ephemeral test container. Credentials stay
in a generated ignored env file and process environment, never in CLI args.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from uuid import uuid4

import psycopg

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=root/"test-results/planning-benchmark")
args = parser.parse_args()
sys.path[:0] = [str(root/"backend"), str(root/"etl")]
from app.services.simulation.planning import store
from app.services.simulation.planning.context import build_context, preflight
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.jobs import process_one


def command(arguments):
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError("Docker test command failed: "+result.stderr[-1000:])
    return result.stdout.strip()


runtime = root/".runtime/planning-postgres-check"
runtime.mkdir(parents=True, exist_ok=True)
env_file = runtime/(uuid4().hex+".env")
password = secrets.token_urlsafe(32)
env_file.write_text(f"POSTGRES_PASSWORD={password}\nPOSTGRES_USER=planning_test\nPOSTGRES_DB=planning_test\n", encoding="utf-8")
name = "planning-store-test-"+uuid4().hex[:12]
created, started = False, time.perf_counter()
try:
    command(["docker", "run", "--detach", "--rm", "--name", name, "--env-file", str(env_file),
             "--publish", "127.0.0.1::5432", "postgis/postgis:16-3.5"])
    created = True
    ports = json.loads(command(["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", name]))
    port = ports["5432/tcp"][0]["HostPort"]
    os.environ.pop("PLANNING_SQLITE_PATH", None)
    os.environ["DATABASE_URL"] = f"postgresql://planning_test:{password}@127.0.0.1:{port}/planning_test"
    os.environ["SIMULATION_WORK_DIR"] = str(runtime/"solvers")
    os.environ["PLANNING_BENCHMARK_MACHINE_ID"] = "isolated-postgres-local-worker"
    deadline = time.monotonic()+60
    while True:
        if time.monotonic() > deadline:
            raise RuntimeError("Isolated PostgreSQL/PostGIS did not become ready")
        try:
            with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as connection:
                extension = connection.execute("SELECT extversion FROM pg_extension WHERE extname='postgis'").fetchone()
                if extension:
                    break
        except psycopg.Error:
            if time.monotonic() > deadline:
                raise RuntimeError("Isolated PostgreSQL did not become ready") from None
        time.sleep(.5)
    payload = demo_study()
    payload["projects"], payload["options"] = payload["projects"][:1], payload["options"][:1]
    payload["conditions"] = {"traffic_hours": [18]}
    study = PlanningStudy(**payload)
    context = build_context(study)
    assert preflight(study)["runtime_estimates"]["native"]["status"] == "unavailable"
    saved = store.save_study(context["inputs"], context["sha256"])
    first = store.enqueue(saved["id"], "native", "postgres-native-first")
    assert store.enqueue(saved["id"], "native", "postgres-native-first")["id"] == first["id"]
    done = process_one()
    assert done["status"] == "succeeded", done["status"]
    result = store.load_document(done["result_id"], "run")
    assert all(result["validity"].values())
    assert result["execution_path"] == "single_site_shared_context"
    assert result["child_cache"]["computed"] == 5 and result["child_cache"]["hits"] == 0
    assert len(store.children(first["id"])) == 5
    timing = preflight(study)["runtime_estimates"]["native"]
    assert timing["status"] == "measured_example" and timing["sample_count"] == 1
    assert timing["reference_run_ids"] == [done["result_id"]]
    assert result["runtime"]["benchmark_eligible"]
    store.enqueue(saved["id"], "native", "postgres-native-reuse")
    reused = process_one()
    cached = store.load_document(reused["result_id"], "run")
    assert cached["child_cache"]["hits"] == 5 and cached["child_cache"]["computed"] == 0
    assert not cached["runtime"]["benchmark_eligible"]
    assert preflight(study)["runtime_estimates"]["native"]["sample_count"] == 1
    assert result["baseline"] == cached["baseline"] and result["options"] == cached["options"]
    revision = store.save_study(context["inputs"], context["sha256"], saved["id"])
    assert revision["parent_revision_id"] == saved["id"]
    assert store.load_document(saved["id"], "study") == saved
    store.enqueue(saved["id"], "screening", "postgres-cancel")
    owner = store.claim()
    store.cancel(owner["id"])
    assert not store.heartbeat(owner, {})
    assert store.finish(owner, cancelled=True)["status"] == "cancelled"
    store.retry(owner["id"])
    successor = store.claim()
    assert successor["lease_id"] != owner["lease_id"]
    assert not store.heartbeat(owner, {})
    store.finish(successor, error="Deliberate storage-contract failure")
    with store.transaction() as session:
        assert session.postgres
        assert session.execute("SELECT COUNT(*) FROM planning_child_cache").fetchone()[0] == 5
    report = {"status": "passed", "model_version": context["model_version"], "seconds": time.perf_counter()-started, "postgis_version": extension[0],
              "checks": ["native SUMO/SWMM", "PostgreSQL child cache", "immutable study revision", "idempotency", "cancel", "retry and lease fencing", "cold runtime benchmark; cached job excluded"],
              "runtime_estimate": timing,
              "first_computed": 5, "second_cache_hits": 5, "second_computed": 0}
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output/"postgres-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
finally:
    try:
        if created:
            command(["docker", "rm", "--force", name])
    finally:
        env_file.unlink(missing_ok=True)
