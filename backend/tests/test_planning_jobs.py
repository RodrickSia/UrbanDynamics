from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from threading import Event

import psutil
import pytest

from app.services.simulation.planning import store, identity
from app.services.simulation.planning.cache import ChildExecutor
from app.services.simulation.planning.context import build_context
from app.services.simulation.planning.models import PlanningStudy
from app.services.simulation.planning.presets import demo_study
from app.services.simulation.planning.recovery import recover
from app.services.simulation.planning.runner import execute
from app.services.simulation.planning.jobs import Cancelled
from app.services.simulation.integrated.solvers import SolverUnavailable, manifest


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"jobs.sqlite"))
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path/"solvers"))
    monkeypatch.setenv("PLANNING_MAX_RUNNING", "2")
    (tmp_path/"solvers").mkdir()


def queued(key):
    study = PlanningStudy(**demo_study())
    context = build_context(study)
    saved = store.save_study(context["inputs"], context["sha256"])
    return store.enqueue(saved["id"], "native", key)


def checkpoint(job):
    def check(progress):
        if not store.heartbeat(job, progress):
            raise Cancelled()
    return check


def test_partial_children_retry_immutability_fencing_and_validated_cache(tmp_path):
    pending = queued("partial-retry")
    owner = store.claim()
    cache = ChildExecutor(owner, checkpoint(owner))
    directory = tmp_path/"solvers"/"test-child"
    directory.mkdir()
    (directory/"result.txt").write_text("complete data")
    computed = {"value": 10, "artifacts": manifest(directory, "test", "1")}
    assert cache.run("context-one", "test", {"input": 1}, lambda: computed) == computed
    original_child = store.children(owner["id"])[0]
    assert store.finish(owner, error="later child failed")["status"] == "partial"
    assert store.get_job(owner["id"])["result_id"] is None
    assert store.retry(owner["id"])["status"] == "queued"
    assert store.retry(owner["id"])["status"] == "queued"
    resumed = store.claim()
    assert resumed["lease_id"] != owner["lease_id"]
    assert not store.heartbeat(owner, {})
    with pytest.raises(store.Conflict):
        store.finish(owner, result={"invalid": True})
    retry_cache = ChildExecutor(resumed, checkpoint(resumed))
    assert retry_cache.run("context-one", "test", {"input": 1}, lambda: pytest.fail("Completed child ran again")) == computed
    assert retry_cache.hits == 1
    assert store.children(owner["id"])[0]["result_id"] == original_child["result_id"]
    # Artifact tampering causes a real recomputation, never reuse of old bytes.
    (directory/"result.txt").write_text("changed data")
    rebuilt = []
    def rebuild():
        rebuilt.append(True)
        return {"value": 11, "artifacts": manifest(directory, "test", "1")}
    assert retry_cache.run("context-one", "test", {"input": 1}, rebuild)["value"] == 11
    assert rebuilt == [True]
    assert store.load_document(original_child["result_id"], "child")["result"]["value"] == 10
    assert retry_cache.run("different-model-context", "test", {"input": 1}, rebuild)["value"] == 11
    assert len(rebuilt) == 2
    store.finish(resumed, result={"all_complete": True})
    assert store.get_job(pending["id"])["attempts"] == 2
    with pytest.raises(store.Conflict):
        store.retry(pending["id"])


def test_concurrent_identical_children_compute_once_and_do_not_steal_live_lock():
    queued("concurrent-one")
    queued("concurrent-two")
    first, second = store.claim(), store.claim()
    assert store.claim() is None
    started, release, waiting = Event(), Event(), Event()
    count = []
    one = ChildExecutor(first, checkpoint(first))
    def second_progress(progress):
        checkpoint(second)(progress)
        if progress["module"] == "waiting_for_child":
            waiting.set()
    two = ChildExecutor(second, second_progress)
    def compute():
        count.append(1)
        started.set()
        assert release.wait(10)
        return {"complete": True}
    with ThreadPoolExecutor(max_workers=2) as workers:
        a = workers.submit(one.run, "same-context", "test", {}, compute)
        assert started.wait(10)
        b = workers.submit(two.run, "same-context", "test", {}, compute)
        assert waiting.wait(10)
        release.set()
        assert a.result(timeout=10) == b.result(timeout=10)
    assert count == [1] and two.hits == 1


def test_stale_heartbeat_live_owner_not_recovered_and_dead_identity_recovered():
    queued("recover-one")
    owner = store.claim()
    with store.transaction() as session:
        session.execute("UPDATE planning_jobs SET heartbeat=0 WHERE id=?", (owner["id"],))
    assert recover()[0]["owner_state"] == "alive"
    assert store.get_job(owner["id"])["status"] == "running"
    # Record an actual child process as owner, wait for its verified exit.
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(.4)"])
    recorded = identity.snapshot(process.pid)
    with store.transaction() as session:
        import json
        session.execute("UPDATE planning_job_owners SET identity_json=? WHERE job_id=?", (json.dumps(recorded), owner["id"]))
    process.wait(timeout=5)
    assert identity.state(recorded) == "stopped"
    assert recover()[0]["action"] == "recovered"
    assert store.get_job(owner["id"])["status"] == "queued"
    assert not store.heartbeat(owner, {})


def test_timeout_and_cancel_terminate_owned_child_without_result(tmp_path):
    directory = tmp_path/"solvers"/"owned-timeout"
    directory.mkdir()
    seen = []
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(SolverUnavailable, match="time limit"):
        execute(command, directory, lambda p: seen.append(p["child_identity"]), timeout=.1)
    assert seen and identity.state(seen[-1]) == "stopped"
    queued("cancel-real-child")
    owner = store.claim()
    def cancel(progress):
        seen.append(progress["child_identity"])
        store.heartbeat(owner, progress)
        store.cancel(owner["id"])
        checkpoint(owner)(progress)
    with pytest.raises(Cancelled):
        execute(command, directory, cancel)
    assert identity.state(seen[-1]) == "stopped"
    assert store.finish(owner, cancelled=True)["result_id"] is None


def test_remote_and_reused_pid_identity_never_kills_replacement():
    import os
    info = identity.snapshot(os.getpid())
    other = {**info, "host": "different-host"}
    assert identity.state(other) == "unverifiable"
    reused = {**info, "created_at": info["created_at"]-100}
    assert identity.state(reused) == "stopped"
    assert identity.stop_orphan(reused, Path(info["cwd"]).parent)
    assert psutil.pid_exists(os.getpid())


@pytest.mark.parametrize("patch", [{"created_at": None}, {"pid": "invalid"}, {"command_hash": None}, {"cwd": None}])
def test_malformed_owner_kept_without_recovery_or_process_action(patch):
    import json
    queued("unverified-owner")
    owner = store.claim()
    recorded = {**identity.snapshot(__import__("os").getpid()), **patch}
    with store.transaction() as session:
        session.execute("UPDATE planning_job_owners SET identity_json=? WHERE job_id=?", (json.dumps(recorded), owner["id"]))
    assert recover() == [{"job_id": owner["id"], "action": "kept", "owner_state": "unverifiable"}]
    assert store.get_job(owner["id"])["status"] == "running"
    assert identity.state(recorded) == "unverifiable"


def test_unverifiable_descendant_never_terminates_verified_parent(tmp_path):
    directory = tmp_path/"solvers"/"unverified-descendant"
    directory.mkdir()
    process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], cwd=directory)
    try:
        recorded = identity.snapshot(process.pid)
        assert identity.state({**recorded, "created_at": 10**1000}) == "unverifiable"
        recorded["descendants"] = [{}]
        assert not identity.stop_orphan(recorded, directory.parent)
        assert process.poll() is None
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_recovery_stops_verified_orphan_of_dead_worker_only(tmp_path):
    import json
    directory = tmp_path/"solvers"/"orphan"
    directory.mkdir()
    queued("orphan-recovery")
    job = store.claim()
    code = "import subprocess,sys,time,json,os; from app.services.simulation.planning.identity import snapshot,snapshot_tree; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],cwd=sys.argv[1],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(.1); print(json.dumps({'owner':snapshot(os.getpid()),'child':snapshot_tree(p.pid)}),flush=True); time.sleep(.5)"
    owner = subprocess.Popen([sys.executable, "-c", code, str(directory)], stdout=subprocess.PIPE, text=True)
    try:
        recorded = json.loads(owner.stdout.readline())
        owner_info, child = recorded["owner"], recorded["child"]
        assert child["parent_pid"] == owner_info["pid"]
        with store.transaction() as session:
            session.execute("UPDATE planning_job_owners SET identity_json=? WHERE job_id=?", (json.dumps(owner_info), job["id"]))
        store.heartbeat(job, {"module": "solver", "child_pid": child["pid"], "child_identity": child})
        owner.wait(timeout=5)
        assert identity.state(owner_info) == "stopped" and identity.state(child) == "alive"
        assert recover()[0]["action"] == "recovered"
        assert identity.state(child) == "stopped"
        assert all(identity.state(member) == "stopped" for member in child["descendants"])
        assert store.get_job(job["id"])["status"] == "queued"
    finally:
        if owner.poll() is None:
            owner.terminate()
            owner.wait(timeout=5)
        if 'child' in locals() and identity.state(child) == "alive":
            identity.stop_orphan(child, directory.parent)


def test_native_partial_retry_and_second_job_reuse_real_solvers(monkeypatch, tmp_path):
    from app.services.simulation.planning import drainage
    from app.services.simulation.planning.jobs import process_one
    payload = demo_study()
    payload["projects"] = payload["projects"][:1]
    payload["options"] = payload["options"][:1]
    payload["conditions"] = {"traffic_hours": [18]}
    study = PlanningStudy(**payload)
    context = build_context(study)
    saved = store.save_study(context["inputs"], context["sha256"])
    first = store.enqueue(saved["id"], "native", "native-partial")
    real_drainage = drainage.run
    failures = []
    def fail_once(*args, **kwargs):
        if not failures:
            failures.append(True)
            raise SolverUnavailable("Deliberate failure before first SWMM child")
        return real_drainage(*args, **kwargs)
    monkeypatch.setattr(drainage, "run", fail_once)
    partial = process_one()
    assert partial["status"] == "partial" and partial["result_id"] is None
    assert partial["child_counts"]["succeeded"] == 2  # netconvert + actual baseline SUMO
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    available = client.get(f"/api/v1/planning/jobs/{partial['id']}/children")
    assert available.status_code == 200
    child = next(c for c in available.json()["children"] if c["status"] == "succeeded")
    assert client.get(f"/api/v1/planning/jobs/{partial['id']}/children/{child['child_key']}").status_code == 200
    assert client.post(f"/api/v1/planning/jobs/{first['id']}/retry").status_code == 202
    complete = process_one()
    assert complete["status"] == "succeeded"
    result = store.load_document(complete["result_id"], "run")
    assert result["child_cache"]["hits"] == 2 and result["child_cache"]["computed"] == 3
    assert all(result["validity"].values())
    store.enqueue(saved["id"], "native", "native-cache-second-job")
    reused = process_one()
    cached = store.load_document(reused["result_id"], "run")
    assert cached["child_cache"]["hits"] == 5 and cached["child_cache"]["computed"] == 0
    assert cached["baseline"] == result["baseline"] and cached["options"] == result["options"]
    # Corrupt only one actual SUMO artifact. All other child outputs survive.
    directory = tmp_path/"solvers"/cached["baseline"]["traffic"]["runs"][0]["artifacts"]["artifact_id"]
    with (directory/"trips.xml").open("a") as handle:
        handle.write("<!-- deliberate artifact integrity test -->")
    store.enqueue(saved["id"], "native", "native-cache-after-corruption")
    refreshed = process_one()
    rebuilt = store.load_document(refreshed["result_id"], "run")
    assert rebuilt["child_cache"]["hits"] == 4 and rebuilt["child_cache"]["computed"] == 1
    assert all(rebuilt["validity"].values())
