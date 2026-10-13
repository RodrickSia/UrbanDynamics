"""Durable complete child results; checksum-verified artifacts before reuse."""
from copy import deepcopy
from functools import lru_cache
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

from ..integrated.context import digest
from ..integrated.solvers import SolverUnavailable
from . import store


def artifact_root():
    return Path(os.getenv("SIMULATION_WORK_DIR", str(Path(tempfile.gettempdir())/"urban-dynamics-solvers"))).resolve()


def engines():
    import sumo
    from swmm.toolkit import solver
    suffix = ".exe" if os.name == "nt" else ""
    binaries = [Path(sumo.SUMO_HOME)/"bin"/(name+suffix) for name in ("sumo", "netconvert")]
    binaries += [p for p in Path(solver.__file__).parent.rglob("*") if p.is_file() and p.suffix in (".dll", ".pyd", ".so")]
    signatures = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(set(binaries)))
    return {"sumo_package": version("eclipse-sumo"), "swmm_package": version("swmm-toolkit"),
            "python": sys.version, "platform": platform.platform(),
            "binary_hashes": binary_hashes(signatures)}


@lru_cache(maxsize=4)
def binary_hashes(signatures):
    return {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path, _, _ in signatures}


def artifacts_valid(value):
    root = artifact_root()
    if isinstance(value, list):
        return all(artifacts_valid(item) for item in value)
    if not isinstance(value, dict):
        return True
    if "artifact_id" in value and "files" in value:
        directory = (root/value["artifact_id"]).resolve()
        if directory.parent != root or not directory.is_dir() or not value["files"]:
            return False
        for name, expected in value["files"].items():
            file = (directory/name).resolve()
            if file.parent != directory or not file.is_file():
                return False
            raw = file.read_bytes()
            if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
                return False
        return True
    return all(artifacts_valid(item) for item in value.values())


class ChildExecutor:
    def __init__(self, job, checkpoint):
        self.job, self.checkpoint = job, checkpoint
        self.hits = self.computations = 0
        self.versions = engines()

    def run(self, context_hash, kind, details, compute):
        from .jobs import Cancelled
        descriptor = {"context_hash": context_hash, "engine_versions": self.versions, "kind": kind, **details}
        key = digest(descriptor)
        if not store.child_started(self.job, key, descriptor):
            raise Cancelled("Worker no longer owns the child calculation")
        self.checkpoint({"module": "child_start", "child_key": key, "kind": kind})
        started = time.monotonic()
        while True:
            cached = store.cached_child(key, descriptor)
            # A network's paths must still refer to the verified local artifact
            # root; cross-host paths never get silently reinterpreted.
            paths_match = cached is not None and (kind != "network" or Path(cached["result"]["directory"]).resolve() == (artifact_root()/cached["result"]["artifacts"]["artifact_id"]).resolve())
            if cached and paths_match and artifacts_valid(cached["result"]):
                if not store.child_completed(self.job, key, descriptor, cached_document=cached):
                    raise Cancelled("Cancellation requested before cached child registration")
                self.hits += 1
                self.checkpoint({"module": "child_cached", "child_key": key, "kind": kind})
                return deepcopy(cached["result"])
            if store.acquire_child_lock(self.job, key):
                break
            self.checkpoint({"module": "waiting_for_child", "child_key": key, "kind": kind})
            if time.monotonic()-started > 300:
                raise SolverUnavailable("Shared child is still owned by another job; retry later without stopping its owner")
            time.sleep(.25)
        try:
            result = compute()
            if result.get("count_balanced") is False or result.get("balance_passed") is False:
                raise SolverUnavailable("Child solver result failed its conservation gate; not cached")
            if not artifacts_valid(result):
                raise SolverUnavailable("Completed child artifacts could not be verified; not cached")
            if not store.child_completed(self.job, key, descriptor, result=result):
                raise Cancelled("Cancellation requested before child publication")
            self.computations += 1
            self.checkpoint({"module": "child_completed", "child_key": key, "kind": kind})
            return result
        finally:
            store.release_child_lock(self.job, key)
