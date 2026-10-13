"""Multi-project SUMO on a single immutable synthetic corridor and accesses."""
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
import random
from xml.etree import ElementTree as ET

from ..integrated.solvers import workdir, manifest, SolverUnavailable
from .runner import execute


def _rng(seed, group):
    return random.Random(int.from_bytes(hashlib.sha256(f"{seed}:{group}".encode()).digest()[:8], "big"))


def build_network(study, directory, checkpoint=None):
    if study.traffic_network_mode == "osm_snapshot":
        from .osm_network import build
        return build(study, directory, checkpoint)
    try:
        import sumo
    except ImportError as error:
        raise SolverUnavailable("Install the configured eclipse-sumo package") from error
    suffix = ".exe" if os.name == "nt" else ""
    binaries = Path(sumo.SUMO_HOME)/"bin"
    from .network import specification
    spec = specification(study)
    nodes, edges = ET.Element("nodes"), ET.Element("edges")
    for node in spec["nodes"]:
        ET.SubElement(nodes, "node", **{k: str(v) for k, v in node.items()})
    for edge in spec["edges"]:
        ET.SubElement(edges, "edge", **{k: str(v) for k, v in edge.items()})
    ET.ElementTree(nodes).write(directory/"nodes.xml", encoding="utf-8")
    ET.ElementTree(edges).write(directory/"edges.xml", encoding="utf-8")
    execute([str(binaries/("netconvert"+suffix)), "--node-files", "nodes.xml", "--edge-files", "edges.xml",
             "--output-file", "network.xml", "--no-turnarounds", "true"], directory, checkpoint)
    return {"directory": str(directory), "binary": str(binaries/("sumo"+suffix)),
            **{key: spec[key] for key in ("routes", "map", "project_to_physical_parcel", "project_to_solver_parcel", "project_random_keys", "provenance")}}



def run(study, state, network, hour, seed, checkpoint=None):
    directory = workdir("planning-sumo")
    (directory/"network.xml").write_bytes((Path(network["directory"])/"network.xml").read_bytes())
    routes = ET.Element("routes")
    ET.SubElement(routes, "vType", id="car", accel="2.6", decel="4.5", sigma="0.3", length="4.5", minGap="2.5")
    ET.SubElement(routes, "vType", id="motorcycle", vClass="motorcycle", accel="3", decel="5", sigma="0.3", length="2", width=".8", minGap="1", latAlignment="arbitrary")
    for identifier, path in sorted(network["routes"].items()):
        ET.SubElement(routes, "route", id=identifier, edges=" ".join(path))
    vehicles, planned_by_group = [], {}
    def add_group(group, count, kind, choices, stop_seconds=None, random_identity=None):
        planned_by_group[group] = count
        rng = _rng(seed, random_identity or group)
        for index in range(count):
            departure = (index+rng.random())/max(1, count)*3600
            chosen = choices[index % len(choices)]
            vehicles.append((departure, group, index, kind, chosen, stop_seconds))
    profile = state["resolved_background"]["traffic"]
    bikes = profile["motorcycles"][hour]
    background_routes = network.get("background_routes", ["background_west", "background_east"])
    add_group("background_car", profile["cars"][hour], "car", background_routes)
    add_group("background_motorcycle", bikes, "motorcycle", background_routes)
    projects = {p.id: p for p in study.projects}
    for parcel in state["parcels"]:
        identifier = parcel["id"]
        project = projects[identifier]
        design = project.development if parcel["active"] else project.baseline
        for key, kind in (("cars", "car"), ("motorcycles", "motorcycle")):
            count = round(parcel["demand"]["hourly"][key][hour])
            physical_id = network["project_to_solver_parcel"][identifier]
            add_group(f"project_{physical_id}_{kind}", count, kind,
                      network.get("project_routes", {}).get(physical_id, [f"{physical_id}_{direction}_{origin}" for direction in ("in", "out") for origin in ("west", "east")]), design.gate_service_seconds, network["project_random_keys"][identifier]+"_"+kind)
    planned = sum(planned_by_group.values())
    if planned > 8000:
        raise ValueError("Pilot exceeds 8,000 planned vehicles per common-hour run")
    for departure, group, index, kind, route, stop in sorted(vehicles):
        vehicle = ET.SubElement(routes, "vehicle", id=f"{group}__{index}", type=kind, route=route, depart=f"{departure:.3f}", departLane="best")
        if stop is not None:
            gate_edge = next(edge for edge in network["routes"][route] if edge.endswith("_in") or edge.endswith("_out"))
            ET.SubElement(vehicle, "stop", lane=gate_edge+"_0", duration=str(stop))
    ET.ElementTree(routes).write(directory/"routes.xml", encoding="utf-8")
    additional = ET.Element("additional")
    ET.SubElement(additional, "edgeData", id="edges", file="edge-data.xml", period="300", begin="0", end="4200")
    ET.ElementTree(additional).write(directory/"additional.xml", encoding="utf-8")
    execute([network["binary"], "--net-file", "network.xml", "--route-files", "routes.xml", "--additional-files", "additional.xml",
             "--end", "4200", "--seed", str(seed), "--lateral-resolution", ".8", "--no-step-log", "true", "--duration-log.disable", "true",
             "--tripinfo-output", "trips.xml", "--tripinfo-output.write-unfinished", "true", "--summary-output", "summary.xml",
             "--queue-output", "queues.xml", "--queue-output.period", "30", "--time-to-teleport", "-1"], directory, checkpoint)
    trips = list(ET.parse(directory/"trips.xml").getroot().findall("tripinfo"))
    completed = [t for t in trips if float(t.get("arrival", "-1")) >= 0]
    unfinished = [t for t in trips if float(t.get("arrival", "-1")) < 0]
    last = ET.parse(directory/"summary.xml").getroot().findall("step")[-1]
    departed = int(float(last.get("inserted", "0")))
    queues = [float(lane.get("queueing_length", "0")) for step in ET.parse(directory/"queues.xml").getroot() for lane in step.iter("lane")]
    cohorts = {}
    for group, count in planned_by_group.items():
        done = [t for t in completed if t.get("id", "").rsplit("__", 1)[0] == group]
        cohort_trips = [t for t in trips if t.get("id", "").rsplit("__", 1)[0] == group]
        cohorts[group] = {"planned": count, "completed": len(done), "departed": len(cohort_trips),
                          "mean_completed_delay_seconds": sum(float(t.get("timeLoss", "0")) for t in done)/len(done) if done else None}
    intervals = []
    for interval in ET.parse(directory/"edge-data.xml").getroot():
        intervals.append({"begin_seconds": float(interval.get("begin")), "end_seconds": float(interval.get("end")),
                          "edges": [{"edge_id": e.get("id"), **{k: float(e.get(k)) for k in ("speed", "traveltime", "entered", "left", "occupancy", "timeLoss") if e.get(k) is not None}} for e in interval]})
    completed_fraction = len(completed)/planned if planned else 1
    from .timeseries import queue_intervals
    lane_queues = queue_intervals(directory, intervals)
    def cohort_delay(prefix):
        members = [value for key, value in cohorts.items() if key.startswith(prefix)]
        count = sum(member["completed"] for member in members)
        return sum((member["mean_completed_delay_seconds"] or 0)*member["completed"] for member in members)/count if count else None
    return {"engine": "SUMO", "source_kind": "mixed_demo" if study.traffic_network_mode == "osm_snapshot" else "synthetic", "hour_local": hour, "seed": seed,
            "planned_vehicles": planned, "completed_vehicles": len(completed), "departed_vehicles": departed,
            "unfinished_vehicles": len(unfinished), "undeparted_vehicles": planned-departed,
            "completed_fraction": completed_fraction,
            "mean_completed_delay_seconds": sum(float(t.get("timeLoss", "0")) for t in completed)/len(completed) if completed else None,
            "background_completed_delay_seconds": cohort_delay("background_"),
            "project_completed_delay_seconds": cohort_delay("project_"),
            "max_queue_length_m": max(queues, default=0), "cohorts": cohorts, "edge_intervals": intervals,
            "queue_intervals": lane_queues,
            "project_to_solver_parcel": network["project_to_solver_parcel"],
            "count_balanced": 0 <= departed <= planned and departed == len(trips) and int(float(last.get("ended", "0"))) == len(completed) and planned == len(completed)+len(unfinished)+(planned-departed),
            "delay_comparability": "all_planned_trips_completed" if completed_fraction == 1 else "incomplete_trip_bias",
            "network_provenance": network["provenance"], "artifacts": manifest(directory, "SUMO", version("eclipse-sumo")),
            "limitations": ["External-OD-only: no project-to-project trip capture or local camera calibration.",
                            "Population, mode shares, vehicle behaviour and signal timings are scenario assumptions.",
                            "Delay refers to completed trips; evaluate backlog and background cohorts alongside it."]}
