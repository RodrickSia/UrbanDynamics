"""Standalone, estimated-demand SUMO traffic runs (separate from planning studies)."""

from __future__ import annotations

import fcntl
import gzip
import json
import logging
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from shutil import rmtree
from uuid import UUID, uuid4

from src.shared.database import connect_to_warehouse

LOS_COLORS = {
    "A": "#168a58",
    "B": "#71ad45",
    "C": "#d2b83f",
    "D": "#e58b32",
    "E": "#d9583c",
    "F": "#8c3047",
}
SIMULATION_SECONDS = 6 * 60 * 60
TOTAL_TRIP_PERIOD_SECONDS = 60.0
PLANNED_TOTAL_TRIPS_6H = int(SIMULATION_SECONDS / TOTAL_TRIP_PERIOD_SECONDS)
MOTORCYCLE_SHARE = 0.7
PLANNED_MOTORCYCLE_TRIPS_6H = round(PLANNED_TOTAL_TRIPS_6H * MOTORCYCLE_SHARE)
PLANNED_CAR_TRIPS_6H = PLANNED_TOTAL_TRIPS_6H - PLANNED_MOTORCYCLE_TRIPS_6H
SIMULATION_TIMEOUT_SECONDS = int(os.getenv("TRAFFIC_SIMULATION_TIMEOUT_SECONDS", "12600"))
TRIP_GENERATION_TIMEOUT_SECONDS = int(
    os.getenv("TRAFFIC_TRIP_GENERATION_TIMEOUT_SECONDS", "3600")
)
ROUTE_BUILD_TIMEOUT_SECONDS = int(os.getenv("TRAFFIC_ROUTE_BUILD_TIMEOUT_SECONDS", "1800"))
NETWORK_BUILD_TIMEOUT_SECONDS = int(os.getenv("TRAFFIC_NETWORK_BUILD_TIMEOUT_SECONDS", "1800"))
SIMULATION_MODEL = "mesoscopic-6h-mixed-motorcycle-v1"
logger = logging.getLogger(__name__)


def _directories() -> tuple[Path, Path]:
    data = Path(os.getenv("DATA_DIR", "/data"))
    runtime = Path(os.getenv("TRAFFIC_SIMULATION_DIR", "/runtime/traffic-prediction"))
    return data, runtime


def _sumo_home() -> Path:
    try:
        import sumo
    except ImportError as error:
        raise RuntimeError("SUMO is not installed in the traffic prediction service") from error
    return Path(sumo.SUMO_HOME)


def _run(command: list[str], cwd: Path, timeout: int) -> None:
    environment = dict(os.environ)
    home = _sumo_home()
    environment["SUMO_HOME"] = str(home)
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(home / "tools"), environment.get("PYTHONPATH", "")) if item
    )
    started = time.monotonic()
    stage = Path(command[0]).name
    logger.info("Starting SUMO stage %s (timeout=%ss)", stage, timeout)
    try:
        subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            check=True,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        logger.info(
            "SUMO stage %s finished in %.1fs",
            Path(command[0]).name,
            time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as error:
        stderr = error.stderr or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stderr_tail = stderr[-1400:]
        logger.error(
            "SUMO stage %s timed out after %.1fs; stderr tail: %s",
            stage,
            time.monotonic() - started,
            stderr_tail or "(empty)",
        )
        detail = f"; stderr tail: {stderr_tail}" if stderr_tail else ""
        raise RuntimeError(
            f"SUMO stage {stage} exceeded its {timeout}s time limit{detail}"
        ) from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "SUMO command failed")[-1200:]
        raise RuntimeError(detail) from error


def _network_file(data: Path, runtime: Path) -> Path:
    """Reuse a prepared HCMC network or build it once in the shared runtime volume."""
    network_dir = runtime / "network"
    network_dir.mkdir(parents=True, exist_ok=True)
    source = data / "osm_sumo_hcmc" / "hcmc.osm.pbf"
    prepared = data / "osm_sumo_hcmc" / "hcmc.net.xml"
    if not source.is_file():
        raise FileNotFoundError(f"HCMC OSM input is missing: {source}")
    if (
        prepared.is_file()
        and prepared.stat().st_size > 0
        and prepared.stat().st_mtime >= source.stat().st_mtime
    ):
        return prepared
    network = network_dir / "hcmc.net.xml"
    with (network_dir / ".build.lock").open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if (
            network.is_file()
            and network.stat().st_size > 0
            and network.stat().st_mtime >= source.stat().st_mtime
        ):
            return network
        home = _sumo_home()
        osmium = os.getenv("OSMIUM_BINARY", "osmium")
        netconvert = home / "bin" / ("netconvert.exe" if os.name == "nt" else "netconvert")
        pbf_xml = network_dir / "hcmc.osm.xml"
        if (
            not pbf_xml.is_file()
            or pbf_xml.stat().st_size == 0
            or pbf_xml.stat().st_mtime < source.stat().st_mtime
        ):
            pbf_temporary = network_dir / "hcmc.osm.building.xml"
            pbf_temporary.unlink(missing_ok=True)
            try:
                _run(
                    [osmium, "cat", str(source), "--output", str(pbf_temporary), "--overwrite"],
                    network_dir,
                    300,
                )
                pbf_temporary.replace(pbf_xml)
            finally:
                pbf_temporary.unlink(missing_ok=True)

        temporary = network_dir / f"hcmc.net.building-{os.getpid()}.xml"
        type_map = home / "data" / "typemap" / "osmNetconvert.typ.xml"
        if not type_map.is_file():
            raise FileNotFoundError(f"SUMO OSM type map is missing: {type_map}")
        temporary.unlink(missing_ok=True)
        try:
            _run(
                [
                    str(netconvert),
                    "--osm-files",
                    str(pbf_xml),
                    "--output-file",
                    str(temporary),
                    "--type-files",
                    str(type_map),
                    "--junctions.join",
                    "--tls.guess-signals",
                    "--roundabouts.guess",
                    "--output.street-names",
                    "--proj.utm",
                    "--no-turnarounds",
                ],
                network_dir,
                NETWORK_BUILD_TIMEOUT_SECONDS,
            )
            temporary.replace(network)
        finally:
            temporary.unlink(missing_ok=True)
        return network


def _target_demand(weekday: int, period: str) -> tuple[float, int]:
    """Use a fixed, deliberately low synthetic mixed-fleet demand for the six-hour layer."""
    del weekday, period  # Scenario identity does not alter this minimal test demand.
    return TOTAL_TRIP_PERIOD_SECONDS, 0


def _entered_by_edge(intervals: list[ET.Element]) -> dict[str, int]:
    entered: dict[str, int] = {}
    for interval in intervals:
        for element in interval.findall("edge"):
            edge_id = element.get("id", "")
            if edge_id and not edge_id.startswith(":"):
                entered[edge_id] = entered.get(edge_id, 0) + int(
                    float(element.get("entered", "0"))
                )
    return entered


def _features_from_intervals(
    network,
    intervals: list[ET.Element],
    run_id: str,
    weekday: int,
    period: str,
    trip_period: float,
    observation_rows: int,
    road_edges: tuple[tuple[str, list[list[float]], float], ...] | None = None,
    car_intervals: list[ET.Element] | None = None,
    motorcycle_intervals: list[ET.Element] | None = None,
) -> dict:
    if not intervals:
        raise RuntimeError("SUMO completed without edge-level output")
    entered_by_edge = _entered_by_edge(intervals)
    entered_cars_by_edge = _entered_by_edge(car_intervals or [])
    entered_motorcycles_by_edge = _entered_by_edge(motorcycle_intervals or [])
    sampled_seconds_by_edge: dict[str, float] = {}
    speed_seconds_by_edge: dict[str, float] = {}
    occupancy_seconds_by_edge: dict[str, float] = {}
    for interval in intervals:
        for element in interval.findall("edge"):
            edge_id = element.get("id", "")
            if not edge_id or edge_id.startswith(":"):
                continue
            sampled = float(element.get("sampledSeconds", "0"))
            if sampled > 0:
                sampled_seconds_by_edge[edge_id] = sampled_seconds_by_edge.get(edge_id, 0) + sampled
                speed_seconds_by_edge[edge_id] = speed_seconds_by_edge.get(edge_id, 0) + (
                    float(element.get("speed", "0")) * sampled
                )
                occupancy_seconds_by_edge[edge_id] = occupancy_seconds_by_edge.get(edge_id, 0) + (
                    float(element.get("occupancy", "0")) * sampled
                )

    features = []
    if road_edges is None:
        road_edges = tuple(
            (
                edge.getID(),
                [network.convertXY2LonLat(x, y) for x, y in edge.getShape()],
                float(edge.getSpeed()),
            )
            for edge in network.getEdges()
            if not edge.getID().startswith(":") and len(edge.getShape()) >= 2
        )
    for edge_id, coordinates, free_speed in road_edges:
        sampled = sampled_seconds_by_edge.get(edge_id, 0)
        # SUMO reports no measured speed when an edge has no sampled car. Use
        # free-flow speed for that zero-volume edge rather than painting it as jammed.
        simulated_speed = speed_seconds_by_edge.get(edge_id, 0) / sampled if sampled else free_speed
        ratio = simulated_speed / free_speed if free_speed > 0 else 0
        grade = (
            "A"
            if ratio >= 0.9
            else "B"
            if ratio >= 0.8
            else "C"
            if ratio >= 0.65
            else "D"
            if ratio >= 0.5
            else "E"
            if ratio >= 0.35
            else "F"
        )
        features.append(
            {
                "type": "Feature",
                "id": edge_id,
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {
                    "edge_id": edge_id,
                    "simulated_los": grade,
                    "color": LOS_COLORS[grade],
                    "simulated_speed_kmh": round(simulated_speed * 3.6, 1),
                    "free_flow_speed_kmh": round(free_speed * 3.6, 1),
                    "speed_ratio": round(ratio, 3),
                    "congestion_score": round((1 - min(1, ratio)) * 100, 1),
                    "simulated_vehicles_6h": entered_by_edge.get(edge_id, 0),
                    "simulated_cars_6h": entered_cars_by_edge.get(edge_id, 0),
                    "simulated_motorcycles_6h": entered_motorcycles_by_edge.get(edge_id, 0),
                    "occupancy_percent": round(
                        occupancy_seconds_by_edge.get(edge_id, 0) / sampled if sampled else 0, 1
                    ),
                },
            }
        )
    if not features:
        raise RuntimeError("SUMO produced no map-ready road edge results")
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "run_id": run_id,
            "engine": "SUMO",
            "simulation_model": SIMULATION_MODEL,
            "weekday": weekday,
            "period": period,
            "timezone": "Asia/Ho_Chi_Minh",
            "simulation_duration_hours": SIMULATION_SECONDS / 3600,
            "simulation_interval_seconds": (
                float(intervals[-1].get("end", "0")) - float(intervals[0].get("begin", "0"))
            ),
            "vehicle_count_period_seconds": SIMULATION_SECONDS,
            "vehicle_count_period_label": "simulated 6-hour period",
            "vehicle_count_type": "passenger cars and motorcycles",
            "max_simulated_vehicles_6h": max(
                (feature["properties"]["simulated_vehicles_6h"] for feature in features),
                default=0,
            ),
            "total_trip_period_seconds": trip_period,
            "planned_total_trips_6h": PLANNED_TOTAL_TRIPS_6H,
            "planned_car_trips_6h": PLANNED_CAR_TRIPS_6H,
            "planned_motorcycle_trips_6h": PLANNED_MOTORCYCLE_TRIPS_6H,
            "motorcycle_share": MOTORCYCLE_SHARE,
            "historical_observation_rows_used": observation_rows,
            "demand_method": (
                "Fixed low-load synthetic rate: 360 planned vehicle trip attempts across six hours, "
                "split 70% motorcycles and 30% passenger cars; not observed demand, vehicle counts, "
                "or an origin-destination matrix"
            ),
            "simulated_modes": ["passenger_car", "motorcycle"],
            "motorcycles_simulated": True,
            "stuck_vehicle_teleport_after_seconds": 300,
            "interpretation": (
                "Standalone six-hour, low-demand mixed car/motorcycle SUMO scenario output; not live traffic, "
                "observed congestion, or a validated forecast."
            ),
            "features": len(features),
        },
    }


@lru_cache(maxsize=2)
def _cached_road_edges(network_path: str) -> tuple[tuple[str, list[list[float]], float], ...]:
    """Load/transform the static road graph once per worker process."""
    import sumolib

    network = sumolib.net.readNet(network_path)
    return tuple(
        (
            edge.getID(),
            [list(network.convertXY2LonLat(x, y)) for x, y in edge.getShape()],
            float(edge.getSpeed()),
        )
        for edge in network.getEdges()
        if not edge.getID().startswith(":") and len(edge.getShape()) >= 2
    )


def _features(
    network_path: Path,
    output_path: Path,
    run_id: str,
    weekday: int,
    period: str,
    trip_period: float,
    observation_rows: int,
) -> dict:
    road_edges = _cached_road_edges(str(network_path.resolve()))
    root = ET.parse(output_path / "edge-data.xml").getroot()
    car_root = ET.parse(output_path / "car-edge-data.xml").getroot()
    motorcycle_root = ET.parse(output_path / "motorcycle-edge-data.xml").getroot()
    return _features_from_intervals(
        None,
        root.findall("interval"),
        run_id,
        weekday,
        period,
        trip_period,
        observation_rows,
        road_edges,
        car_intervals=car_root.findall("interval"),
        motorcycle_intervals=motorcycle_root.findall("interval"),
    )


def run_prediction(weekday: int, period: str, run_id: str | None = None) -> dict:
    data, runtime = _directories()
    runtime.mkdir(parents=True, exist_ok=True)
    network_path = _network_file(data, runtime)
    trip_period, observations = _target_demand(weekday, period)
    run_id = run_id or str(uuid4())
    run_root = runtime / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    directory = run_root / f"attempt-{uuid4().hex}"
    directory.mkdir(parents=True)
    home = _sumo_home()
    binaries = home / "bin"
    suffix = ".exe" if os.name == "nt" else ""
    random_trips = home / "tools" / "randomTrips.py"
    if not random_trips.is_file():
        raise FileNotFoundError(f"SUMO randomTrips tool is missing: {random_trips}")
    vehicle_types = ET.Element("additional")
    ET.SubElement(
        vehicle_types,
        "vType",
        id="car",
        vClass="passenger",
        accel="2.6",
        decel="4.5",
        sigma="0.5",
        length="4.5",
        minGap="2.5",
    )
    ET.SubElement(
        vehicle_types,
        "vType",
        id="motorcycle",
        vClass="motorcycle",
        guiShape="motorcycle",
        length="2.2",
        minGap="2.5",
    )
    ET.ElementTree(vehicle_types).write(
        directory / "vehicle-types.xml", encoding="utf-8", xml_declaration=True
    )
    modes = (
        ("car", "passenger", PLANNED_CAR_TRIPS_6H),
        ("motorcycle", "motorcycle", PLANNED_MOTORCYCLE_TRIPS_6H),
    )
    for vehicle_type, edge_permission, planned_trips in modes:
        _run(
            [
                sys.executable,
                str(random_trips),
                "--net-file",
                str(network_path),
                "--output-trip-file",
                f"{vehicle_type}-trips.xml",
                "--begin",
                "0",
                "--end",
                str(SIMULATION_SECONDS),
                "--period",
                str(SIMULATION_SECONDS / planned_trips),
                "--seed",
                "17",
                "--prefix",
                vehicle_type,
                "--fringe-factor",
                "5",
                "--additional-file",
                "vehicle-types.xml",
                "--edge-permission",
                edge_permission,
                "--trip-attributes",
                f'type="{vehicle_type}"',
            ],
            directory,
            TRIP_GENERATION_TIMEOUT_SECONDS,
        )
    _run(
        [
            str(binaries / ("duarouter" + suffix)),
            "--net-file",
            str(network_path),
            "--route-files",
            "car-trips.xml,motorcycle-trips.xml",
            "--additional-files",
            "vehicle-types.xml",
            "--output-file",
            "routes.xml",
            "--ignore-errors",
            "true",
        ],
        directory,
        ROUTE_BUILD_TIMEOUT_SECONDS,
    )
    root = ET.Element("additional")
    # Total traffic drives the layer color and speed/LOS; extra detectors
    # preserve per-mode passage counts for the feature inspector.
    for detector_id, output_file, vehicle_types_filter in (
        ("traffic", "edge-data.xml", "car motorcycle"),
        ("cars", "car-edge-data.xml", "car"),
        ("motorcycles", "motorcycle-edge-data.xml", "motorcycle"),
    ):
        ET.SubElement(
            root,
            "edgeData",
            id=detector_id,
            file=output_file,
            period=str(SIMULATION_SECONDS),
            begin="0",
            end=str(SIMULATION_SECONDS),
            excludeEmpty="false",
            vTypes=vehicle_types_filter,
        )
    ET.ElementTree(root).write(directory / "additional.xml", encoding="utf-8", xml_declaration=True)
    _run(
        [
            str(binaries / ("sumo" + suffix)),
            "--net-file",
            str(network_path),
            "--route-files",
            "routes.xml",
            "--additional-files",
            "additional.xml,vehicle-types.xml",
            "--begin",
            "0",
            "--end",
            str(SIMULATION_SECONDS),
            "--seed",
            "17",
            "--no-step-log",
            "true",
            "--duration-log.disable",
            "true",
            "--time-to-teleport",
            "300",
            "--mesosim",
            "true",
        ],
        directory,
        SIMULATION_TIMEOUT_SECONDS,
    )
    return _features(network_path, directory, run_id, weekday, period, trip_period, observations)


def read_result(run_id: str) -> dict | None:
    try:
        canonical = str(UUID(run_id))
    except ValueError:
        return None
    _, runtime = _directories()
    path = runtime / "runs" / canonical / "result.geojson"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def cleanup_run(run_id: str) -> None:
    """Remove per-run SUMO scratch files after the result is stored in PostGIS."""
    try:
        canonical = str(UUID(run_id))
    except ValueError:
        return
    _, runtime = _directories()
    rmtree(runtime / "runs" / canonical, ignore_errors=True)


def read_cached_result(run_id: str) -> dict | None:
    """Read a persisted result when the worker's shared runtime file is unavailable."""
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            SELECT result_gzip
            FROM transport.sumo_congestion_scenario_cache
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(gzip.decompress(row[0]))


def cached_scenario(weekday: int, period: str) -> dict | None:
    """Return cache identity and metadata for a weekday/half-hour, if computed."""
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            SELECT run_id, metadata
            FROM transport.sumo_congestion_scenario_cache
            WHERE weekday = %s AND period = %s
              AND metadata->>'simulation_model' = %s
            """,
            (weekday, period, SIMULATION_MODEL),
        ).fetchone()
    if row is None:
        return None
    return {"run_id": str(row[0]), "metadata": row[1]}


def latest_cached_scenario() -> dict | None:
    """Return the newest six-hour scenario published by the offline workflow."""
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            SELECT run_id, weekday, period, metadata, generated_at
            FROM transport.sumo_congestion_scenario_cache
            WHERE metadata->>'simulation_model' = %s
            ORDER BY generated_at DESC, run_id DESC
            LIMIT 1
            """,
            (SIMULATION_MODEL,),
        ).fetchone()
    if row is None:
        return None
    return {
        "run_id": str(row[0]),
        "weekday": int(row[1]),
        "period": row[2].strftime("%H:%M"),
        "metadata": row[3],
        "generated_at": row[4],
    }


def catalog() -> dict:
    data, _ = _directories()
    has_network_input = (data / "osm_sumo_hcmc" / "hcmc.osm.pbf").is_file()
    try:
        with connect_to_warehouse() as connection:
            edges, observations, queue_ready = connection.execute(
                """
                SELECT (SELECT count(*) FROM transport.sumo_edge),
                       (SELECT count(*) FROM transport.traffic_observation
                        WHERE sumo_edge_id IS NOT NULL),
                       to_regclass('transport.sumo_congestion_run') IS NOT NULL
                """
            ).fetchone()
    except Exception:
        return {
            "available": False,
            "network_input": has_network_input,
            "network_edges": 0,
            "matched_observations": 0,
            "queue_ready": False,
        }
    return {
        "available": has_network_input and edges > 0 and queue_ready,
        "network_input": has_network_input,
        "network_edges": edges,
        "matched_observations": observations,
        "queue_ready": queue_ready,
    }
