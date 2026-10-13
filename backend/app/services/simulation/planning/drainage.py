"""Separate catchments each have one shared SWMM graph and background area."""
import json
import math
import sys

from shapely.geometry import shape, Point, LineString, mapping
from shapely.ops import transform

from ..integrated.context import projection
from ..integrated.solvers import workdir, manifest
from .runner import execute
from .parcels import registry


def combine_runoff(catchments):
    """Aggregate aligned report samples; reject equal-length shifted grids."""
    if not catchments or len({c["catchment_id"] for c in catchments}) != len(catchments):
        raise ValueError("Catchment hydrographs must be nonempty and unique")
    reference = None
    values = []
    for catchment in catchments:
        series = catchment["timeseries"]
        minute = series["minute"]
        runoff = series["runoff_m3_s"]
        step = series["sample_interval_seconds"] / 60
        if not minute or len(minute) != len(runoff) or not math.isfinite(step) or step <= 0:
            raise ValueError("Catchment hydrograph has invalid reporting samples")
        if any(not math.isfinite(v) or v < 0 for v in runoff) or any(not math.isfinite(t) for t in minute):
            raise ValueError("Catchment hydrograph contains nonfinite or negative runoff")
        if minute[0] <= 0 or any(abs((b-a)-step) > 1e-9 for a, b in zip(minute, minute[1:])):
            raise ValueError("Catchment reporting timestamps must follow their positive uniform step")
        grid = (step, tuple(minute))
        if reference is not None and grid != reference:
            raise ValueError("Catchments have incompatible reporting time grids")
        reference = grid
        values.append(runoff)
    combined = [math.fsum(point) for point in zip(*values)]
    peak = max(combined)
    return {"minute": list(reference[1]), "runoff_m3_s": combined, "peak_m3_s": peak,
            "peak_minute": reference[1][combined.index(peak)] if peak > 0 else None,
            "sample_interval_seconds": reference[0]*60}


def run(study, state, library, catchment, checkpoint=None):
    directory = workdir("planning-swmm")
    soil = library["swmm"]
    parcels = [p for p in state["parcels"] if p["catchment_id"] == catchment.id]
    projects = {p.id: p for p in study.projects}
    physical_ids = registry(study)
    rain_intensity = study.conditions.rainfall_mm*60/study.conditions.rainfall_duration_minutes
    end_minutes = study.conditions.rainfall_duration_minutes+180
    header = f"""[TITLE]
Synthetic regional shared drainage graph, not an observed sewer
[OPTIONS]
FLOW_UNITS CMS
INFILTRATION HORTON
FLOW_ROUTING DYNWAVE
START_DATE 04/15/2026
START_TIME 00:00:00
REPORT_START_DATE 04/15/2026
REPORT_START_TIME 00:00:00
END_DATE 04/15/2026
END_TIME {end_minutes//60:02d}:{end_minutes%60:02d}:00
WET_STEP 00:01:00
DRY_STEP 00:01:00
ROUTING_STEP 00:00:05
REPORT_STEP 00:01:00
ALLOW_PONDING NO
[EVAPORATION]
CONSTANT 0
[RAINGAGES]
R1 INTENSITY 0:05 1 TIMESERIES RAIN
[TIMESERIES]
"""
    for minute in range(0, end_minutes+5, 5):
        value = rain_intensity if minute < study.conditions.rainfall_duration_minutes else 0
        header += f"RAIN 04/15/2026 {minute//60:02d}:{minute%60:02d} {value}\n"
    header += "[SUBCATCHMENTS]\n"
    subcatchments, nodes, conduits, xsections, storages, orifices = [], [], [], [], [], []
    forward, backward = projection(shape(study.study_area.model_dump()))
    points = [transform(forward, shape(projects[p["id"]].site.model_dump())).centroid for p in parcels]
    cx = sum(p.x for p in points)/len(points) if points else 0
    cy = sum(p.y for p in points)/len(points) if points else 0
    node_map = {"J0": (cx, cy+150), "O0": (cx+250, cy+150)}
    if catchment.background_area_m2:
        area = catchment.background_area_m2
        subcatchments.append(("background", "J0", area, catchment.background_impervious_percent))
    for parcel, point in zip(parcels, points):
        identifier = physical_ids[parcel["id"]]
        project = projects[parcel["id"]]
        design = project.development if parcel["active"] else project.baseline
        outlet = f"S_{identifier}" if design.storage_m3 else f"J_{identifier}"
        for kind, area in parcel["geometry"]["surfaces_m2"].items():
            if area > .01:
                impervious = {"roof": 100, "paved": 100, "green": 0, "permeable": soil["permeable_impervious_percent"]}[kind]
                subcatchments.append((f"{identifier}_{kind}", outlet, area, impervious))
        nodes.append(f"J_{identifier} 12 2 0 0 0")
        node_map[f"J_{identifier}"] = (point.x, point.y)
        length = max(30, math.dist((point.x, point.y), node_map["J0"]))
        conduits.append(f"C_{identifier} J_{identifier} J0 {length} {library['drain_manning_n']} 0 0 0 0")
        xsections.append(f"C_{identifier} CIRCULAR {catchment.branch_diameter_m} 0 0 0 1")
        if design.storage_m3:
            area = max(10, design.storage_m3/2)
            storages.append(f"S_{identifier} 12 {design.storage_m3/area} {design.storage_initial_m3/area} FUNCTIONAL {area} 0 0 0 0")
            orifices.append(f"OR_{identifier} S_{identifier} J_{identifier} SIDE 0 {soil['orifice_discharge_coefficient']} NO 0")
            xsections.append(f"OR_{identifier} CIRCULAR {design.storage_outlet_diameter_m} 0 0 0 1")
            node_map[f"S_{identifier}"] = (point.x, point.y+20)
    for name, outlet, area, impervious in subcatchments:
        header += f"{name} R1 {outlet} {area/10000} {impervious} {area**.5} {soil['surface_slope_percent']} 0\n"
    header += "[SUBAREAS]\n"
    for name, *_ in subcatchments:
        header += f"{name} {soil['impervious_manning_n']} {soil['pervious_manning_n']} {soil['impervious_depression_mm']} {soil['pervious_depression_mm']} {soil['zero_depression_percent']} OUTLET\n"
    header += "[INFILTRATION]\n"
    for name, *_ in subcatchments:
        header += f"{name} {soil['horton_max_mm_hour']} {soil['horton_min_mm_hour']} {soil['horton_decay_per_hour']} {soil['dry_days']} 0\n"
    header += "[JUNCTIONS]\nJ0 10 2 0 0 0\n"+"\n".join(nodes)+"\n[OUTFALLS]\nO0 8 FREE NO\n"
    header += "[CONDUITS]\nTRUNK J0 O0 250 "+str(library["drain_manning_n"])+" 0 0 0 0\n"+"\n".join(conduits)
    header += f"\n[XSECTIONS]\nTRUNK CIRCULAR {catchment.trunk_diameter_m} 0 0 0 1\n"+"\n".join(xsections)+"\n"
    if storages:
        header += "[STORAGE]\n"+"\n".join(storages)+"\n[ORIFICES]\n"+"\n".join(orifices)+"\n"
    header += "[REPORT]\nINPUT NO\nCONTINUITY YES\nFLOWSTATS YES\nSUBCATCHMENTS ALL\nNODES ALL\nLINKS ALL\n"
    (directory/"drainage.inp").write_text(header, encoding="utf-8")
    execute([sys.executable, "-m", "app.services.simulation.integrated.swmm_worker", str(directory), "--detailed"], directory, checkpoint)
    result = json.loads((directory/"result.json").read_text(encoding="utf-8"))
    result["timeseries"]["sample_interval_seconds"] = 60
    result["hourly_label"] = "1-minute samples; event plus 3-hour recession"
    result.update(engine="SWMM", source_kind="synthetic", catchment_id=catchment.id,
                  background_area_m2=catchment.background_area_m2,
                  registered_parcel_area_m2=sum(sum(p["geometry"]["surfaces_m2"].values()) for p in parcels),
                  source=catchment.source, artifacts=manifest(directory, "SWMM", result["version"]),
                  limitations="Synthetic elevations, pipes, soil and free outfall; no tide, 2D flood depth or sanitary coupling. Overflow is report-sample integration, not continuity-ledger volume.")
    result["map"] = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": f"{catchment.id}:{node['id']}", "geometry": mapping(transform(backward, Point(node_map[node["id"]]))),
         "properties": {**node, "catchment_id": catchment.id, "source_kind": "synthetic"}} for node in result["nodes"]]}
    link_endpoints = {"TRUNK": ("J0", "O0")}
    for parcel in parcels:
        identifier = physical_ids[parcel["id"]]
        link_endpoints[f"C_{identifier}"] = (f"J_{identifier}", "J0")
        if f"S_{identifier}" in node_map:
            link_endpoints[f"OR_{identifier}"] = (f"S_{identifier}", f"J_{identifier}")
    result["link_map"] = {"type": "FeatureCollection", "features": []}
    for identifier, series in result["timeseries"]["links"].items():
        origin, destination = link_endpoints[identifier]
        result["link_map"]["features"].append({"type": "Feature", "id": f"{catchment.id}:{identifier}",
            "geometry": mapping(transform(backward, LineString([node_map[origin], node_map[destination]]))),
            "properties": {"link_id": identifier, "from_node": origin, "to_node": destination,
                           "catchment_id": catchment.id, "source_kind": "synthetic",
                           "peak_abs_flow_m3_s": max(map(abs, series["flow_m3_s"]), default=0),
                           "peak_depth_m": max(series["depth_m"], default=0)}})
    return result
