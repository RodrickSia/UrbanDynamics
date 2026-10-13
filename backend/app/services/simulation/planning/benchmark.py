"""Observed cold-job timing for compatible worker/model/input profiles.

No extrapolation to new physical workloads, queue latency or artifact download.
"""
import os
import platform
import statistics
import sys

from ..integrated.context import digest
from . import store


def _physical(value):
    if isinstance(value, dict):
        return {key: _physical(item) for key, item in value.items()
                if key not in ("title", "source", "source_note", "baseline_source", "criteria")}
    if isinstance(value, list):
        return [_physical(item) for item in value]
    return value


def profile(study, context, mode, versions=None):
    machine = os.getenv("PLANNING_BENCHMARK_MACHINE_ID")
    if not machine:
        return None
    native = mode == "native" or mode == "uncertainty" and study.uncertainty and study.uncertainty.engine == "native"
    if native and versions is None:
        from .cache import engines
        versions = engines()
    if not native:
        versions = {"python": sys.version, "platform": platform.platform()}
    signature = {"model_version": context["model_version"], "mode": mode,
                 "machine": machine, "engines_sha256": digest(versions),
                 "physical_input_sha256": digest({"inputs": _physical(context["inputs"]), "library": context["library"]})}
    return {**signature, "sha256": digest(signature)}


def measurement(study, context, mode, seconds, executor=None):
    result = {"compute_seconds": seconds,
              "scope": "Worker calculation before result persistence; excludes queue wait, ZIP and download",
              "cache_hits": executor.hits if executor else 0,
              "computed_children": executor.computations if executor else 0,
              "benchmark_eligible": False}
    key = profile(study, context, mode, executor.versions if executor else None)
    # Cached/mixed jobs measure another cost model and must not lower cold ETA.
    if key and (executor is None or executor.hits == 0):
        result.update(benchmark_eligible=True, benchmark_profile=key)
    return result


def estimate(study, context, mode):
    unavailable = {"status": "unavailable", "estimated_compute_seconds": None,
                   "note": "No matching measured worker/model/physical-workload benchmark; solver counts remain available. No realtime promise."}
    try:
        key = profile(study, context, mode)
        if key is None:
            return unavailable
        samples = store.benchmark_samples(key["sha256"])
    except (store.StoreError, ImportError, OSError):
        return unavailable
    if not samples:
        return unavailable
    seconds = [sample["compute_seconds"] for sample in samples]
    return {"status": "measured_example" if len(samples) == 1 else "observed_range",
            "estimated_compute_seconds": statistics.median(seconds),
            "min_observed_seconds": min(seconds), "max_observed_seconds": max(seconds),
            "sample_count": len(samples), "profile_sha256": key["sha256"],
            "reference_run_ids": [sample["run_id"] for sample in samples],
            "scope": "Cold worker computation before persistence; queue, ZIP and download excluded",
            "note": "Observed examples, not a confidence interval or deadline; changed physics/engines/machine require new evidence."}
