"""Run real native solvers in isolated processes, with bounded workloads."""
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET


class SolverUnavailable(RuntimeError):
    pass


def workdir(engine):
    root = Path(os.getenv("SIMULATION_WORK_DIR", str(Path(tempfile.gettempdir()) / "urban-dynamics-solvers"))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=engine+"-", dir=root))


def execute(command, cwd, timeout=60):
    try:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[4]) + os.pathsep + environment.get("PYTHONPATH", "")
        result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SolverUnavailable("Simulation engine unavailable or exceeded time limit") from error
    if result.returncode:
        (cwd / "failure.log").write_text(result.stdout+result.stderr, encoding="utf-8")
        raise SolverUnavailable(f"Simulation engine failed; artifact {cwd.name}/failure.log")
    return result.stdout


def manifest(directory, engine, version):
    return {"artifact_id": directory.name, "engine": engine, "version": version,
            "files": {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
                      for p in directory.iterdir() if p.is_file()}}


def traffic(design, demand, context):
    try:
        import sumo
    except ImportError as error:
        raise SolverUnavailable("Install pinned eclipse-sumo dependency") from error
    directory = workdir("sumo")
    binary_directory = Path(sumo.SUMO_HOME) / "bin"
    suffix = ".exe" if os.name == "nt" else ""
    binary = binary_directory / ("sumo"+suffix)
    netconvert = binary_directory / ("netconvert"+suffix)
    # Scenario graph, not the city's road network. Both directions and traffic signals are explicit.
    (directory/"nodes.xml").write_text('<nodes><node id="w" x="-250" y="0"/><node id="c" x="0" y="0" type="traffic_light"/>'
                                        '<node id="e" x="250" y="0"/><node id="g" x="0" y="100"/></nodes>', encoding="utf-8")
    edges = ET.Element("edges")
    for a, b in (("w", "c"), ("c", "w"), ("c", "e"), ("e", "c"), ("c", "g"), ("g", "c")):
        ET.SubElement(edges, "edge", id=a+b, **{"from": a, "to": b, "numLanes": str(design.gate_lanes if "g" in a+b else 2),
                      "speed": "8.33" if "g" in a+b else "13.89", "priority": "1" if "g" in a+b else "2"})
    ET.ElementTree(edges).write(directory/"edges.xml", encoding="utf-8")
    execute([str(netconvert), "--node-files", "nodes.xml", "--edge-files", "edges.xml", "--output-file", "network.xml",
             "--no-turnarounds", "true"], directory)
    routes = ET.Element("routes")
    ET.SubElement(routes, "vType", id="car", accel="2.6", decel="4.5", sigma="0.3", length="4.5", width="1.8", minGap="2.5")
    ET.SubElement(routes, "vType", id="motorcycle", vClass="motorcycle", accel="3", decel="5", sigma="0.3",
                  length="2", width=".8", minGap="1", latAlignment="arbitrary")
    for name, value in {"through_w": "wc ce", "through_e": "ec cw", "in": "wc cg", "out": "gc ce"}.items():
        ET.SubElement(routes, "route", id=name, edges=value)
    peak = max(range(24), key=lambda h: demand["hourly"]["cars"][h]+demand["hourly"]["motorcycles"][h])
    car_count = round(demand["hourly"]["cars"][peak])
    bike_count = round(demand["hourly"]["motorcycles"][peak])
    background = context["library"]["background_vehicles_hour"]
    planned = background+car_count+bike_count
    if planned > 8000:
        raise ValueError("Pilot traffic workload exceeds 8,000 vehicles in the peak-hour scenario")
    rng = random.Random(context["seed"])
    vehicles = []
    for group, count, kind in (("background", background, "car"), ("project_car", car_count, "car"),
                               ("project_motorcycle", bike_count, "motorcycle")):
        for i in range(count):
            departure = (i+rng.random())/max(1, count)*3600
            route = ("through_w" if i % 2 else "through_e") if group == "background" else ("in" if i % 2 else "out")
            vehicles.append((departure, group, i, kind, route))
    for departure, group, i, kind, route in sorted(vehicles):
        vehicle = ET.SubElement(routes, "vehicle", id=f"{group}_{i}", type=kind, route=route,
                                depart=f"{departure:.3f}", departLane="best")
        if group != "background":
            # An actual stop on the gate lane models entrance/exit service and its queue.
            ET.SubElement(vehicle, "stop", lane="cg_0" if route == "in" else "gc_0", endPos="75",
                          duration=str(design.gate_service_seconds))
    ET.ElementTree(routes).write(directory/"routes.xml", encoding="utf-8")
    output = execute([str(binary), "--net-file", "network.xml", "--route-files", "routes.xml", "--end", "4200",
                      "--seed", str(context["seed"]), "--lateral-resolution", ".8", "--no-step-log", "true",
                      "--duration-log.disable", "true", "--tripinfo-output", "trips.xml", "--tripinfo-output.write-unfinished", "true",
                      "--summary-output", "summary.xml", "--queue-output", "queues.xml", "--queue-output.period", "60",
                      "--statistic-output", "statistics.xml", "--time-to-teleport", "-1"], directory)
    (directory/"engine.log").write_text(output, encoding="utf-8")
    trips = list(ET.parse(directory/"trips.xml").getroot().findall("tripinfo"))
    completed = [t for t in trips if float(t.get("arrival", "-1")) >= 0]
    summary = ET.parse(directory/"summary.xml").getroot().findall("step")
    last = summary[-1].attrib
    departed = int(float(last.get("inserted", "0")))
    queues = [float(l.get("queueing_length", "0")) for step in ET.parse(directory/"queues.xml").getroot()
              for l in step.iter("lane")]
    statistics = ET.parse(directory/"statistics.xml").getroot()
    safety = statistics.find("safety")
    return {"engine": "SUMO", "version": "1.27.1", "kind": "synthetic", "peak_hour_local": peak,
            "planned_vehicles": planned, "project_vehicles": car_count+bike_count, "departed_vehicles": departed,
            "completed_vehicles": len(completed), "unfinished_vehicles": departed-len(completed),
            "undeparted_vehicles": max(0, planned-departed),
            "mean_completed_delay_seconds": sum(float(t.get("timeLoss", "0")) for t in completed)/max(1, len(completed)),
            "mean_departed_wait_seconds": sum(float(t.get("waitingTime", "0")) for t in trips)/max(1, len(trips)),
            "max_queue_length_m": max(queues, default=0),
            "collisions": int(safety.get("collisions", "0")) if safety is not None else None,
            "simulation_seconds": 4200, "network": {"type": "FeatureCollection", "features": context["roads"]},
            "artifacts": manifest(directory, "SUMO", "1.27.1"),
            "limitations": "Synthetic signalized graph, OD and vehicle behaviour; selected peak-hour only. Gate service uses lane 0; extra gate lanes change approach, not service-station count. Incomplete trips are reported separately; mean delay excludes them."}


def drainage(design, surfaces, context):
    directory = workdir("swmm")
    library = context["library"]
    soil = library["swmm"]
    rain = library["rainfall_mm"]
    target = "S1" if design.storage_m3 else "J1"
    header = f"""[TITLE]
Synthetic pilot drainage; common elevation datum in metres
[OPTIONS]
FLOW_UNITS CMS
INFILTRATION HORTON
FLOW_ROUTING DYNWAVE
START_DATE 04/15/2026
START_TIME 00:00:00
REPORT_START_DATE 04/15/2026
REPORT_START_TIME 00:00:00
END_DATE 04/15/2026
END_TIME 03:00:00
WET_STEP 00:01:00
DRY_STEP 00:01:00
ROUTING_STEP 00:00:05
REPORT_STEP 00:05:00
ALLOW_PONDING NO
[EVAPORATION]
CONSTANT 0
[RAINGAGES]
R1 INTENSITY 1:00 1 TIMESERIES RAIN
[TIMESERIES]
RAIN 04/15/2026 00:00 {rain}
RAIN 04/15/2026 01:00 0
RAIN 04/15/2026 02:00 0
[SUBCATCHMENTS]
"""
    selected = {k: v for k, v in surfaces.items() if v > .01}
    for key, area in selected.items():
        impervious = {"roof": 100, "paved": 100, "permeable": soil['permeable_impervious_percent'], "green": 0}[key]
        header += f"{key} R1 {target} {area/10000} {impervious} {area**.5} {soil['surface_slope_percent']} 0\n"
    header += "[SUBAREAS]\n"
    for key in selected:
        header += f"{key} {soil['impervious_manning_n']} {soil['pervious_manning_n']} {soil['impervious_depression_mm']} {soil['pervious_depression_mm']} {soil['zero_depression_percent']} OUTLET\n"
    header += "[INFILTRATION]\n"
    for key in selected:
        header += f"{key} {soil['horton_max_mm_hour']} {soil['horton_min_mm_hour']} {soil['horton_decay_per_hour']} {soil['dry_days']} 0\n"
    header += f"""[JUNCTIONS]
J1 10 2 0 0 0
[OUTFALLS]
O1 8 FREE NO
[CONDUITS]
C1 J1 O1 200 {library['drain_manning_n']} 0 0 0 0
[XSECTIONS]
C1 CIRCULAR {library['drain_diameter_m']} 0 0 0 1
"""
    if design.storage_m3:
        storage_area = max(10, design.storage_m3/2)
        max_depth = design.storage_m3/storage_area
        initial_depth = design.storage_initial_m3/storage_area
        header += f"""[STORAGE]
S1 10 {max_depth} {initial_depth} FUNCTIONAL {storage_area} 0 0 0 0 0
[ORIFICES]
OR1 S1 J1 SIDE 0 {soil['orifice_discharge_coefficient']} NO 0
[XSECTIONS]
OR1 CIRCULAR {design.storage_outlet_diameter_m} 0 0 0 1
"""
    header += "[REPORT]\nINPUT NO\nCONTINUITY YES\nFLOWSTATS YES\nSUBCATCHMENTS ALL\nNODES ALL\nLINKS ALL\n"
    (directory/"drainage.inp").write_text(header, encoding="utf-8")
    execute([sys.executable, "-m", "app.services.simulation.integrated.swmm_worker", str(directory)], directory)
    result = json.loads((directory/"result.json").read_text(encoding="utf-8"))
    result.update(engine="SWMM", kind="synthetic", artifacts=manifest(directory, "SWMM", result["version"]),
                  limitations="Synthetic drainage, flat terrain and Horton soil parameters; outfall is free, no tide. Node flooding loss is not a 2D depth map. Sanitary demand is calculated separately, not hydraulically coupled.")
    return result
