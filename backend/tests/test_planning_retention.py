import os
import subprocess
import time

import pytest

from app.services.simulation.planning import store
from app.services.simulation.planning.retention import collect


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("PLANNING_SQLITE_PATH", str(tmp_path/"store.sqlite"))
    monkeypatch.setenv("SIMULATION_WORK_DIR", str(tmp_path/"solvers"))
    root = tmp_path/"solvers"
    root.mkdir()
    return root


def old_directory(root, name):
    directory = root/name
    directory.mkdir()
    file = directory/"result.txt"
    file.write_text("solver output")
    old = time.time() - 10*86400
    os.utime(file, (old, old))
    os.utime(directory, (old, old))
    return directory


def test_retention_preserves_nested_run_and_retry_artifacts(isolated):
    retained = old_directory(isolated, "planning-sumo-retained")
    retry = old_directory(isolated, "planning-network-retry")
    orphan = old_directory(isolated, "planning-swmm-orphan")
    unrelated = old_directory(isolated, "sumo-single-site")
    recent = old_directory(isolated, "planning-sumo-recent")
    os.utime(recent/"result.txt", None)
    with store.transaction() as session:
        store._save(session, "run", {"cases": [{"artifacts": {"artifact_id": retained.name, "files": {"result.txt": {}}}}]})
        store._save(session, "child", {"artifacts": {"artifact_id": retry.name, "files": {"result.txt": {}}}})
    report = collect()
    assert report["candidates"] == [orphan.name]
    assert orphan.exists() and not report["deleted"]
    applied = collect(apply=True, exclusive_root=True)
    assert applied["deleted"] == [orphan.name]
    assert not orphan.exists()
    assert all(p.exists() for p in (retained, retry, unrelated, recent))
    assert collect()["candidates"] == []


def test_retention_requires_exclusivity_idle_store_and_valid_age(isolated):
    orphan = old_directory(isolated, "planning-swmm-orphan")
    with pytest.raises(ValueError, match="exclusive"):
        collect(apply=True)
    for age in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            collect(min_age_days=age)
    saved = store.save_study({}, "hash")
    pending = store.enqueue(saved["id"], "native", "retention")
    with pytest.raises(store.Conflict, match="queued or running"):
        collect(apply=True, exclusive_root=True)
    job = store.claim()
    with pytest.raises(store.Conflict):
        collect()
    store.finish(job, cancelled=True)
    assert collect()["candidates"] == [orphan.name]
    assert store.get_job(pending["id"])["status"] == "cancelled"


def test_retention_rejects_bad_stored_paths(isolated):
    orphan = old_directory(isolated, "planning-swmm-orphan")
    with store.transaction() as session:
        store._save(session, "child", {"artifacts": {"artifact_id": "../outside", "files": {"a": {}}}})
    with pytest.raises(ValueError, match="Invalid stored"):
        collect(apply=True, exclusive_root=True)
    assert orphan.exists()


def test_retention_skips_external_link(isolated, tmp_path):
    outside = tmp_path/"outside"
    outside.mkdir()
    link = isolated/"planning-sumo-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("Host does not permit creating symlinks")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "New-Item -ItemType Junction -Path $env:RETENTION_TEST_LINK -Target $env:RETENTION_TEST_TARGET -ErrorAction Stop"],
                       env={**os.environ, "RETENTION_TEST_LINK": str(link), "RETENTION_TEST_TARGET": str(outside)},
                       check=True, capture_output=True)
    report = collect()
    assert {"id": link.name, "reason": "linked_or_outside_root"} in report["skipped"]
    assert outside.exists()
