"""Bounded, object-specific time series from immutable saved runs."""
from copy import deepcopy

from .map_output import LayerUnavailable, LAYER_UNITS


def series(document, option_id, name, object_id, offset=0, limit=60, hour=7, seed=None, catchment_id=None):
    if offset < 0 or not 1 <= limit <= 300:
        raise KeyError("Series offset/limit outside bounds")
    if option_id == "baseline":
        state = document["baseline"]
    else:
        option = next((o for o in document["options"]+document["phases"] if o["id"] == option_id), None)
        if option is None:
            raise KeyError("Unknown option/phase")
        state = option["state"]
    if name == "roads":
        if catchment_id is not None:
            raise KeyError("Traffic series does not use a catchment selector")
        runs = state.get("traffic", {}).get("runs", [])
        if not runs:
            raise LayerUnavailable("Run native simulation to obtain SUMO time series")
        run = next((r for r in runs if r["hour_local"] == hour and (seed is None or r["seed"] == seed)), None)
        if run is None:
            raise KeyError("Traffic hour/seed is not in this run")
        if not any(f["properties"]["edge_id"] == object_id for f in document["spatial_artifacts"]["roads"]["features"]):
            raise KeyError("Unknown road object ID")
        total = len(run["edge_intervals"])
        samples = []
        for index in range(offset, min(total, offset+limit)):
            sample = run["edge_intervals"][index]
            edge = next((e for e in sample["edges"] if e["edge_id"] == object_id), None)
            queues = run.get("queue_intervals", [])
            queue_sample = queues[index] if index < len(queues) else None
            queue = next((e for e in queue_sample["edges"] if e["edge_id"] == object_id), None) if queue_sample else None
            values = {key: edge.get(key) if edge else None for key in LAYER_UNITS["roads"] if key != "sampled_peak_queue_m"}
            values["sampled_peak_queue_m"] = queue.get("sampled_peak_queue_m") if queue else None
            samples.append({"sample_index": index, "begin_seconds": sample["begin_seconds"], "end_seconds": sample["end_seconds"],
                            "values": values, "sample_status": "reported" if edge else "no_reported_sample",
                            "queue_sample_status": "reported" if queue else "no_reported_queue" if queue_sample else "legacy_unavailable"})
        selectors = {"hour_local": hour, "seed": run["seed"]}
        module, engine = "traffic", "SUMO"
        method = "SUMO edge output intervals; queue is the maximum reported lane sample, not lane sum. Missing reports remain null."
        units = LAYER_UNITS["roads"]
    elif name in ("drainage", "drainage_links", "runoff"):
        if seed is not None:
            raise KeyError("SWMM series does not use a random seed selector")
        catchments = state.get("drainage", {}).get("catchments", [])
        if not catchments:
            raise LayerUnavailable("Run native simulation to obtain SWMM time series")
        catchment = next((c for c in catchments if c["catchment_id"] == catchment_id), None)
        if catchment is None:
            raise KeyError("Select a catchment ID from this run")
        data = catchment["timeseries"]
        if name == "runoff":
            if object_id != catchment_id:
                raise KeyError("Runoff object ID must equal the catchment ID")
            values = {"runoff_m3_s": data["runoff_m3_s"]}
            units = {"runoff_m3_s": "m3/s"}
        else:
            group = "nodes" if name == "drainage" else "links"
            if group not in data:
                raise LayerUnavailable("Saved run has no detailed SWMM series; create a new revision")
            if object_id not in data[group]:
                raise KeyError("Unknown SWMM object ID in this catchment")
            values = data[group][object_id]
            units = {key: LAYER_UNITS[name][key] for key in values}
        total = len(data["minute"])
        if any(len(v) != total for v in values.values()):
            raise LayerUnavailable("Saved SWMM series has inconsistent timestamps")
        samples = [{"sample_index": index, "minute": data["minute"][index],
                    "values": {key: value[index] for key, value in values.items()}, "sample_status": "reported"}
                   for index in range(offset, min(total, offset+limit))]
        selectors = {"catchment_id": catchment_id, "sample_interval_seconds": data.get("sample_interval_seconds")}
        module, engine = "drainage", "SWMM"
        method = "Saved SWMM report samples; depth is model depth, not mapped 2D flood depth."
    else:
        raise KeyError("Unknown time-series layer")
    if offset > total:
        raise KeyError("Series offset exceeds the sample count")
    coverage = document["context"].get("data_coverage", {}).get("modules", {}).get(module)
    return deepcopy({"run_id": document.get("id"), "study_id": document.get("study_id"),
                     "option_id": option_id, "phase_id": option_id if any(p["id"] == option_id for p in document["phases"]) else None,
                     "layer": name, "source_object_id": object_id, "selectors": selectors,
                     "engine": engine, "source_kind": "synthetic", "context_hash": document["context"]["sha256"],
                     "source_manifest_id": document["context"].get("snapshot_manifest_id"),
                     "source_ids": coverage["source_ids"] if coverage else [], "module_coverage": coverage,
                     "units": units, "method": method, "samples": samples,
                     "pagination": {"offset": offset, "limit": limit, "count": len(samples), "total": total,
                                    "next_offset": offset+len(samples) if offset+len(samples) < total else None}})
