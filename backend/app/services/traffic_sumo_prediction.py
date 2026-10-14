"""Standalone, estimated-demand SUMO traffic runs (separate from planning studies)."""

from __future__ import annotations

import fcntl
import gzip
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
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
SIMULATION_SECONDS = 1800
SIMULATION_TIMEOUT_SECONDS = int(os.getenv("TRAFFIC_SIMULATION_TIMEOUT_SECONDS", "600"))
MOTORCYCLE_SHARE = 0.7


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
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("SUMO traffic run exceeded its time limit") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "SUMO command failed")[-1200:]
        raise RuntimeError(detail) from error


def _network_file(data: Path, runtime: Path) -> Path:
    """Build and cache a SUMO network from the committed HCMC OSM PBF if needed."""
    network_dir = runtime / "network"
    network_dir.mkdir(parents=True, exist_ok=True)
    source = data / "osm_sumo_hcmc" / "hcmc.osm.pbf"
    prepared = data / "osm_sumo_hcmc" / "hcmc.net.xml"
    if not source.is_file():
        raise FileNotFoundError(f"HCMC OSM input is missing: {source}")
    if prepared.is_file() and prepared.stat().st_mtime >= source.stat().st_mtime:
        return prepared
    network = network_dir / "hcmc.net.xml"
    with (network_dir / ".build.lock").open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if network.is_file() and network.stat().st_mtime >= source.stat().st_mtime:
            return network
        home = _sumo_home()
        osmium = os.getenv("OSMIUM_BINARY", "osmium")
        netconvert = home / "bin" / ("netconvert.exe" if os.name == "nt" else "netconvert")
        pbf_xml = network_dir / "hcmc.osm.xml"
        _run(
            [osmium, "cat", str(source), "--output", str(pbf_xml), "--overwrite"], network_dir, 300
        )
        temporary = network.with_suffix(".building.xml")
        type_map = home / "data" / "typemap" / "osmNetconvert.typ.xml"
        if not type_map.is_file():
            raise FileNotFoundError(f"SUMO OSM type map is missing: {type_map}")
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
            300,
        )
        temporary.replace(network)
        return network


def _target_demand(weekday: int, period: str) -> tuple[float, int]:
    """Translate observed LOS into a documented global demand prior, never counts."""
    hour_text, minute_text = period.split(":", 1)
    slot = int(hour_text) * 2 + int(minute_text) // 30
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            WITH target_period AS (
                SELECT avg(CASE los WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2
                                    WHEN 'D' THEN 3 WHEN 'E' THEN 4 ELSE 5 END) AS mean_los,
                       count(*) AS sample_rows
                FROM transport.traffic_observation
                WHERE sumo_edge_id IS NOT NULL
                  AND extract(isodow FROM observed_at)::integer = %s
                  AND (extract(hour FROM observed_at)::integer * 2
                       + extract(minute FROM observed_at)::integer / 30) = %s
            ), weekday_periods AS (
                SELECT avg(CASE los WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2
                                    WHEN 'D' THEN 3 WHEN 'E' THEN 4 ELSE 5 END) AS mean_los,
                       count(*) AS sample_rows
                FROM transport.traffic_observation
                WHERE sumo_edge_id IS NOT NULL
                  AND extract(isodow FROM observed_at)::integer = %s
            ), all_periods AS (
                SELECT avg(CASE los WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2
                                    WHEN 'D' THEN 3 WHEN 'E' THEN 4 ELSE 5 END) AS mean_los,
                       count(*) AS sample_rows
                FROM transport.traffic_observation
                WHERE sumo_edge_id IS NOT NULL
            )
            SELECT coalesce(target_period.mean_los, weekday_periods.mean_los, all_periods.mean_los),
                   coalesce(nullif(target_period.sample_rows, 0),
                            nullif(weekday_periods.sample_rows, 0),
                            all_periods.sample_rows, 0)
            FROM target_period CROSS JOIN weekday_periods CROSS JOIN all_periods
        """,
            (weekday, slot, weekday),
        ).fetchone()
    if not row or row[1] == 0:
        raise ValueError("No matched historical LOS observations exist in the traffic history")
    mean_los = float(row[0])
    # Higher observed LOS grades imply a denser estimated trip stream. This is a
    # scenario prior, not a measured vehicle count or a fitted OD matrix.
    trip_period_seconds = max(1.5, min(5.0, 4.8 - mean_los * 0.62))
    return trip_period_seconds, int(row[1])


def _features_from_intervals(
    network,
    intervals: list[ET.Element],
    run_id: str,
    weekday: int,
    period: str,
    trip_period: float,
    observation_rows: int,
) -> dict:
    if not intervals:
        raise RuntimeError("SUMO completed without edge-level output")
    entered_by_edge: dict[str, int] = {}
    sampled_seconds_by_edge: dict[str, float] = {}
    speed_seconds_by_edge: dict[str, float] = {}
    occupancy_seconds_by_edge: dict[str, float] = {}
    for interval in intervals:
        for element in interval.findall("edge"):
            edge_id = element.get("id", "")
            if not edge_id or edge_id.startswith(":"):
                continue
            entered_by_edge[edge_id] = entered_by_edge.get(edge_id, 0) + int(
                float(element.get("entered", "0"))
            )
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
    for edge in network.getEdges():
        edge_id = edge.getID()
        if edge_id.startswith(":"):
            continue
        coordinates = [network.convertXY2LonLat(x, y) for x, y in edge.getShape()]
        if len(coordinates) < 2:
            continue
        free_speed = float(edge.getSpeed())
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
                    "estimated_cars_30min": entered_by_edge.get(edge_id, 0),
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
            "weekday": weekday,
            "period": period,
            "timezone": "Asia/Ho_Chi_Minh",
            "simulation_interval_seconds": (
                float(intervals[-1].get("end", "0")) - float(intervals[0].get("begin", "0"))
            ),
            "vehicle_count_period_seconds": SIMULATION_SECONDS,
            "vehicle_count_period_label": "simulated 30-minute period",
            "vehicle_count_type": "passenger cars; motorcycles excluded from the count",
            "max_estimated_cars_30min": max(
                (feature["properties"]["estimated_cars_30min"] for feature in features),
                default=0,
            ),
            "estimated_trip_period_seconds": trip_period,
            "historical_observation_rows_used": observation_rows,
            "demand_method": (
                "Global randomTrips rate estimated from mean historical LOS class; "
                "not observed vehicle counts or an OD matrix"
            ),
            "mode_split_assumption": {
                "motorcycle_share": MOTORCYCLE_SHARE,
                "car_share": 1 - MOTORCYCLE_SHARE,
            },
            "interpretation": (
                "Standalone SUMO scenario output, not live traffic or a validated future forecast."
            ),
            "features": len(features),
        },
    }


def _features(
    network_path: Path,
    output_path: Path,
    run_id: str,
    weekday: int,
    period: str,
    trip_period: float,
    observation_rows: int,
) -> dict:
    import sumolib

    network = sumolib.net.readNet(str(network_path))
    root = ET.parse(output_path / "edge-data.xml").getroot()
    return _features_from_intervals(
        network,
        root.findall("interval"),
        run_id,
        weekday,
        period,
        trip_period,
        observation_rows,
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
        accel="3.0",
        decel="5.0",
        sigma="0.5",
        length="2.0",
        width="0.8",
        minGap="0.8",
        maxSpeed="16.7",
        speedFactor="1.1",
        latAlignment="arbitrary",
    )
    ET.ElementTree(vehicle_types).write(
        directory / "vehicle-types.xml", encoding="utf-8", xml_declaration=True
    )
    for kind, share, vehicle_class in (
        ("car", 1 - MOTORCYCLE_SHARE, "passenger"),
        ("motorcycle", MOTORCYCLE_SHARE, "motorcycle"),
    ):
        _run(
            [
                sys.executable,
                str(random_trips),
                "--net-file",
                str(network_path),
                "--output-trip-file",
                f"{kind}-trips.xml",
                "--begin",
                "0",
                "--end",
                str(SIMULATION_SECONDS),
                "--period",
                str(trip_period / share),
                "--seed",
                "17",
                "--prefix",
                kind,
                "--fringe-factor",
                "5",
                "--vehicle-class",
                vehicle_class,
                "--edge-permission",
                vehicle_class,
                "--trip-attributes",
                f'type="{kind}"',
            ],
            directory,
            180,
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
        180,
    )
    root = ET.Element("additional")
    ET.SubElement(
        root,
        "edgeData",
        id="traffic",
        file="edge-data.xml",
        period="300",
        begin="0",
        end=str(SIMULATION_SECONDS),
        excludeEmpty="false",
        vTypes="car",
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
            "-1",
        ],
        directory,
        SIMULATION_TIMEOUT_SECONDS,
    )
    result = _features(network_path, directory, run_id, weekday, period, trip_period, observations)
    result_path = run_root / "result.geojson"
    temporary = result_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    temporary.replace(result_path)
    return result


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
            """,
            (weekday, period),
        ).fetchone()
    if row is None:
        return None
    return {"run_id": str(row[0]), "metadata": row[1]}


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
        "available": has_network_input and edges > 0 and observations > 0 and queue_ready,
        "network_input": has_network_input,
        "network_edges": edges,
        "matched_observations": observations,
        "queue_ready": queue_ready,
    }
