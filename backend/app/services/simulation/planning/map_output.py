"""Map handoff from immutable results, without recomputing simulations."""
from copy import deepcopy

LAYER_MODULE = {"parcels": "geometry", "school": "school", "shadow": "shadow", "roads": "traffic", "drainage": "drainage", "drainage_links": "drainage"}
LAYER_UNITS = {
    "parcels": {"geometry": "degrees EPSG:4326"}, "school": {"students": "students", "distance_m": "m", "walk_minutes": "minutes", "capacity_places": "places", "allocated_places": "places", "reserved_places": "places"},
    "shadow": {"shaded_receiver_m2": "m2", "hour_local": "hour"},
    "roads": {"speed": "m/s", "traveltime": "s", "entered": "vehicles", "left": "vehicles", "occupancy": "%", "timeLoss": "s", "sampled_peak_queue_m": "m (maximum reported lane, sampled every 30s)"},
    "drainage": {"flooding_m3": "m3/event (1-minute sample integration)", "flooding_duration_minutes": "minutes (report samples above threshold)", "peak_depth_m": "m", "depth_m": "m", "flooding_m3_s": "m3/s"},
    "drainage_links": {"peak_abs_flow_m3_s": "m3/s", "peak_depth_m": "m", "flow_m3_s": "m3/s", "depth_m": "m"}}


class LayerUnavailable(ValueError):
    pass


def layer(document, option_id, name, hour=7, seed=None, interval=0, drainage_sample=None):
    if drainage_sample is not None and name not in ("drainage", "drainage_links"):
        raise KeyError("Drainage sample selector requires a SWMM layer")
    if option_id == "baseline":
        state = document["baseline"]
    else:
        option = next((o for o in document["options"]+document["phases"] if o["id"] == option_id), None)
        if option is None:
            raise KeyError("Unknown option/phase")
        state = option["state"]
    time_window = "scenario_state"
    if name == "parcels":
        collection = deepcopy(document["spatial_artifacts"]["parcels"])
        for feature in collection["features"]:
            feature["properties"]["active"] = feature["properties"]["project_id"] in state["active_project_ids"]
    elif name == "school":
        collection = deepcopy(state["school_services"]["map"])
    elif name == "shadow":
        collection = deepcopy(state["shadow"]["map"])
        collection["features"] = [f for f in collection["features"] if f["properties"]["hour_local"] == hour]
        if hour not in (9, 12, 15):
            raise KeyError("Published shadow hours are 9, 12, 15")
        sample = next(row for row in state["shadow"]["hourly"] if row["hour_local"] == hour)
        for feature in collection["features"]:
            feature["properties"]["shaded_receiver_m2"] = sample["shaded_receiver_m2"]
        time_window = {"solar_date": document["inputs"]["conditions"]["solar_date"], "hour_local": hour}
    elif name in ("drainage", "drainage_links"):
        if not state.get("drainage"):
            raise LayerUnavailable("Run native simulation to obtain SWMM nodes")
        collection = {"type": "FeatureCollection", "features": []}
        windows = []
        for catchment in state["drainage"]["catchments"]:
            key = "map" if name == "drainage" else "link_map"
            if key not in catchment:
                raise LayerUnavailable("Saved run has no SWMM link geometry; run a new revision")
            features = deepcopy(catchment[key]["features"])
            if drainage_sample is not None:
                series = catchment["timeseries"]
                if not 0 <= drainage_sample < len(series["minute"]):
                    raise KeyError("Drainage sample is not in this run")
                minute = series["minute"][drainage_sample]
                windows.append(minute)
                for feature in features:
                    props = feature["properties"]
                    identifier = props["id"] if name == "drainage" else props["link_id"]
                    values = series["nodes" if name == "drainage" else "links"][identifier]
                    props.update({metric: samples[drainage_sample] for metric, samples in values.items()})
                    props.update(sample_index=drainage_sample, minute=minute)
            collection["features"].extend(features)
        time_window = "rain_event_and_recession"
        if drainage_sample is not None:
            time_window = {"sample_index": drainage_sample, "minutes": sorted(set(windows)), "sample_interval_seconds": 60}
    elif name == "roads":
        runs = state.get("traffic", {}).get("runs", [])
        if not runs:
            raise LayerUnavailable("Run native simulation to obtain SUMO road metrics")
        run = next((r for r in runs if r["hour_local"] == hour and (seed is None or r["seed"] == seed)), None)
        if run is None or not 0 <= interval < len(run["edge_intervals"]):
            raise KeyError("Traffic hour/seed/interval is not in this run")
        sample = run["edge_intervals"][interval]
        by_edge = {e["edge_id"]: e for e in sample["edges"]}
        queue = run.get("queue_intervals", [])
        queue_sample = queue[interval] if interval < len(queue) else None
        by_queue = {e["edge_id"]: e for e in queue_sample["edges"]} if queue_sample else {}
        collection = deepcopy(document["spatial_artifacts"]["roads"])
        for feature in collection["features"]:
            feature["properties"].update(by_edge.get(feature["properties"]["edge_id"], {}))
            feature["properties"]["sample_status"] = "reported" if feature["properties"]["edge_id"] in by_edge else "no_reported_sample"
            identifier = feature["properties"]["edge_id"]
            project_ids = feature["properties"].get("project_ids", [])
            if project_ids:
                feature["properties"]["project_id"] = next((p for p in project_ids if p in state["active_project_ids"]), project_ids[0])
            feature["properties"].update(sampled_peak_queue_m=by_queue.get(identifier, {}).get("sampled_peak_queue_m"),
                                         queue_sample_status="reported" if identifier in by_queue else "no_reported_queue" if queue_sample else "legacy_unavailable",
                                         queue_lanes=[l for l in queue_sample["lanes"] if l["edge_id"] == identifier] if queue_sample else [],
                                         queue_method=queue_sample["method"] if queue_sample else None)
        time_window = {"hour_local": hour, "seed": run["seed"], "begin_seconds": sample["begin_seconds"], "end_seconds": sample["end_seconds"]}
    else:
        raise KeyError("Unknown layer")
    phase = any(o["id"] == option_id for o in document["phases"])
    manifest = document["context"].get("source_manifest")
    coverage = document["context"].get("data_coverage", {}).get("modules", {}).get(LAYER_MODULE[name])
    for index, feature in enumerate(collection["features"]):
        properties = feature.setdefault("properties", {})
        properties.update(study_id=document.get("study_id"), run_id=document.get("id"),
                          option_id=option_id, phase_id=option_id if phase else None,
                          context_hash=document["context"]["sha256"], source_kind="synthetic", time_window=time_window)
        feature.setdefault("id", f"{name}:{index}")
        properties.update(source_object_id=properties.get("edge_id") or properties.get("link_id") or properties.get("id") or str(feature["id"]),
                          engine={"roads": "SUMO", "drainage": "SWMM", "drainage_links": "SWMM", "school": "shared_school_capacity_allocation", "shadow": "solar_geometry_union", "parcels": "declared_parcel_geometry"}[name],
                          units=deepcopy(LAYER_UNITS[name]),
                          source_manifest_id=manifest["id"] if manifest else None,
                          source_ids=list(coverage["source_ids"]) if coverage else [],
                          coverage_status=coverage["status"] if coverage else "legacy_not_declared")
    collection.update(layer=name, option_id=option_id, source_kind="synthetic",
                      time_window=time_window, context_hash=document["context"]["sha256"],
                      coordinate_reference="EPSG:4326", coverage="Declared synthetic pilot only")
    collection.update(source_manifest_id=manifest["id"] if manifest else None,
                      module_coverage=deepcopy(coverage), units=deepcopy(LAYER_UNITS[name]))
    if document["context"].get("source_kind") == "mixed_demo":
        collection["source_kind"] = "mixed_demo"
        for feature in collection["features"]:
            feature["properties"]["source_kind"] = "mixed_demo"
    return collection
