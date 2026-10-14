"""Fetch live TomTom flow tiles or historical monthly Traffic Stats for HCMC.

Live snapshot: TOMTOM_API_KEY=... uv run --project etl --no-sync python scripts/test_tomtom_traffic.py
Historical month: TOMTOM_TRAFFIC_STATS_API_KEY=... uv run --project etl --no-sync python scripts/test_tomtom_traffic.py --month 2026-09
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# Prefer the environment variable. For a quick local test, you may paste a key
# here, but do not commit a real key to git.
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "PASTE_YOUR_TOMTOM_API_KEY_HERE")
TRAFFIC_STATS_API_KEY = os.getenv(
    "TOMTOM_TRAFFIC_STATS_API_KEY",
    os.getenv("TOMTOM_MOVE_API_KEY", "PASTE_YOUR_MOVE_TRAFFIC_STATS_KEY_HERE"),
)
API_URL = "https://api.tomtom.com/maps/orbis/traffic/tile/flow"
TRAFFIC_STATS_URL = "https://api.tomtom.com/traffic/trafficstats"
# Approximate former HCMC municipal extent. Override with --bbox for your exact
# OSM/SUMO study boundary. At zoom 12 this remains a manageable one-shot fetch.
DEFAULT_HCMC_BBOX = (106.35, 10.34, 107.05, 11.18)  # west, south, east, north
HCMC_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
TILE_EXTENT = 4096
OUTPUT_CSV = Path("etl/data/road_data_tomtom/tomtom_hcmc_traffic_sample.csv")
BOUNDARY_GEOJSON = Path("etl/data/buildings_footprint/hcmc_boundary.geojson")


def tile_xy(latitude: float, longitude: float, zoom: int) -> tuple[int, int]:
    n = 1 << zoom
    x = int((longitude + 180.0) / 360.0 * n)
    lat_rad = math.radians(latitude)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def tile_local_to_lonlat(xy: tuple[float, float], x: int, y: int, zoom: int) -> tuple[float, float]:
    n = 1 << zoom
    px, py = xy
    world_x = x + px / TILE_EXTENT
    world_y = y + py / TILE_EXTENT
    longitude = world_x / n * 360.0 - 180.0
    latitude = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * world_y / n))))
    return longitude, latitude


def lines_from_geometry(geometry: dict) -> list[list[tuple[float, float]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if kind == "LineString":
        return [coords]
    if kind == "MultiLineString":
        return coords
    return []


def to_wkt(geometry: dict, x: int, y: int, zoom: int) -> str:
    lines = []
    for line in lines_from_geometry(geometry):
        points = [tile_local_to_lonlat((float(p[0]), float(p[1])), x, y, zoom) for p in line]
        if len(points) >= 2:
            lines.append("(" + ", ".join(f"{lon:.7f} {lat:.7f}" for lon, lat in points) + ")")
    if not lines:
        return ""
    return f"LINESTRING{lines[0]}" if len(lines) == 1 else f"MULTILINESTRING({', '.join(lines)})"


def bbox_tiles(west: float, south: float, east: float, north: float, zoom: int) -> list[tuple[int, int]]:
    if not (-180 <= west < east <= 180 and -85.0511 <= south < north <= 85.0511):
        raise ValueError("Invalid bbox; expected west,south,east,north in degrees.")
    x0, y1 = tile_xy(south, west, zoom)
    x1, y0 = tile_xy(north, east, zoom)
    tiles = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    if len(tiles) > 100:
        raise ValueError(f"BBox spans {len(tiles)} tiles; reduce bbox or zoom (maximum 100).")
    return tiles


def hcmc_time_period(captured_local: datetime) -> str:
    hour = captured_local.hour
    if 6 <= hour < 10:
        return "morning_peak_06-10"
    if 10 <= hour < 16:
        return "daytime_10-16"
    if 16 <= hour < 20:
        return "evening_peak_16-20"
    if 20 <= hour < 24:
        return "night_20-24"
    return "overnight_00-06"


def month_dates(month: str) -> tuple[str, str]:
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise ValueError("Month must use YYYY-MM format.") from exc
    if first.strftime("%Y-%m") != month:
        raise ValueError("Month must use YYYY-MM format.")
    next_month = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    last = date.fromordinal(next_month.toordinal() - 1)
    earliest_allowed_end = datetime.now(HCMC_TZ).date().toordinal() - 3
    if last.toordinal() > earliest_allowed_end:
        raise ValueError("TomTom requires the end date to be at least 3 days in the past; choose a completed month.")
    return first.isoformat(), last.isoformat()


def load_hcmc_geometry() -> dict:
    with BOUNDARY_GEOJSON.open(encoding="utf-8") as geojson_file:
        collection = json.load(geojson_file)
    features = collection.get("features", [])
    if not features or not features[0].get("geometry"):
        raise ValueError(f"No polygon geometry found in {BOUNDARY_GEOJSON}")
    return features[0]["geometry"]


def shape_to_wkt(shape: list) -> str:
    return "LINESTRING(" + ", ".join(
        f"{float(point[0]):.7f} {float(point[1]):.7f}" for point in shape
    ) + ")" if shape else ""


def fetch_historical_month(month: str, output: Path) -> int:
    if not TRAFFIC_STATS_API_KEY or TRAFFIC_STATS_API_KEY == "PASTE_YOUR_MOVE_TRAFFIC_STATS_KEY_HERE":
        print(
            "Set TOMTOM_TRAFFIC_STATS_API_KEY to your TomTom MOVE / Traffic Stats key. "
            "The Maps API key used for live tiles may not authorize this service.",
            file=sys.stderr,
        )
        return 2
    try:
        start_date, end_date = month_dates(month)
        geometry = load_hcmc_geometry()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    weekdays = ["MON", "TUE", "WED", "THU", "FRI"]
    time_sets = [
        {"name": "All days all day baseline", "timeGroups": [{"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "times": ["00:00-24:00"]}]},
        {"name": "Weekday morning peak 07-09", "timeGroups": [{"days": weekdays, "times": ["07:00-09:00"]}]},
        {"name": "Weekday midday 11-13", "timeGroups": [{"days": weekdays, "times": ["11:00-13:00"]}]},
        {"name": "Weekday evening peak 16-19", "timeGroups": [{"days": weekdays, "times": ["16:00-19:00"]}]},
        {"name": "Weekend daytime 09-18", "timeGroups": [{"days": ["SAT", "SUN"], "times": ["09:00-18:00"]}]},
    ]
    body = {
        "jobName": f"HCMC traffic speeds {month}",
        "distanceUnit": "KILOMETERS",
        "mapType": "ORBIS",
        "network": {
            "name": "Ho Chi Minh City",
            "geometry": geometry,
            "timeZoneId": "Asia/Ho_Chi_Minh",
            "frcs": [0, 1, 2, 3, 4, 5, 6, 7, 8],
            "probeSource": "ALL",
        },
        "dateRange": {"name": month, "from": start_date, "to": end_date},
        "timeSets": time_sets,
    }

    session = requests.Session()
    session.headers.update({"User-Agent": "UrbanDynamics-Traffic-Stats/1.0"})
    created = session.post(
        f"{TRAFFIC_STATS_URL}/areaanalysis/1",
        params={"key": TRAFFIC_STATS_API_KEY}, json=body, timeout=60,
    )
    if not created.ok:
        print(f"Traffic Stats job creation failed: HTTP {created.status_code}: {created.text[:1000]}", file=sys.stderr)
        return 1
    job_id = created.json().get("jobId")
    if not job_id:
        print(f"TomTom response did not contain jobId: {created.text[:1000]}", file=sys.stderr)
        return 1
    print(f"Submitted HCMC monthly Traffic Stats job {job_id}: {start_date} through {end_date}.")

    status_url = f"{TRAFFIC_STATS_URL}/status/1/{job_id}"
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        time.sleep(15)
        status_response = session.get(status_url, params={"key": TRAFFIC_STATS_API_KEY}, timeout=60)
        if not status_response.ok:
            print(f"Status check failed: HTTP {status_response.status_code}: {status_response.text[:500]}", file=sys.stderr)
            return 1
        status = status_response.json()
        state = status.get("jobState")
        print(f"Job {job_id}: {state}")
        if state == "DONE":
            urls = status.get("urls", [])
            if not urls:
                print("Job completed but returned no result URLs.", file=sys.stderr)
                return 1
            result_url = next((url for url in urls if ".json" in url.lower()), urls[0])
            result_response = session.get(result_url, timeout=180)
            if not result_response.ok:
                print(f"Result download failed: HTTP {result_response.status_code}", file=sys.stderr)
                return 1
            content = result_response.content
            if content[:2] == b"\x1f\x8b":
                content = gzip.decompress(content)
            result = json.loads(content)
            raw_output = output.with_suffix(".json")
            raw_output.parent.mkdir(parents=True, exist_ok=True)
            raw_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            network_result = result.get("network", {})
            segments = network_result.get("segmentResults", [])
            time_set_names = {
                item.get("@id"): item.get("name")
                for item in result.get("timeSets", [])
            }
            rows = []
            for segment in segments:
                for stats in segment.get("segmentTimeResults", []):
                    rows.append({
                        "month": month,
                        "time_set_id": stats.get("timeSet"),
                        "time_set_name": time_set_names.get(stats.get("timeSet"), ""),
                        "date_range_id": stats.get("dateRange"),
                        "segment_id": segment.get("segmentId"),
                        "new_segment_id": segment.get("newSegmentId", ""),
                        "street_name": segment.get("streetName", ""),
                        "frc": segment.get("frc"),
                        "speed_limit_kmh": segment.get("speedLimit"),
                        "length_m": segment.get("distance"),
                        "average_speed_kmh": stats.get("averageSpeed"),
                        "median_speed_kmh": stats.get("medianSpeed"),
                        "harmonic_average_speed_kmh": stats.get("harmonicAverageSpeed"),
                        "average_travel_time_s": stats.get("averageTravelTime"),
                        "normalized_sample_size": stats.get("normalizedSampleSize"),
                        "geometry_wkt": shape_to_wkt(segment.get("shape", [])),
                    })
            columns = list(rows[0]) if rows else [
                "month", "time_set_id", "time_set_name", "date_range_id", "segment_id", "new_segment_id",
                "street_name", "frc", "speed_limit_kmh", "length_m", "average_speed_kmh",
                "median_speed_kmh", "harmonic_average_speed_kmh", "average_travel_time_s",
                "normalized_sample_size", "geometry_wkt",
            ]
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            print(f"Saved {len(rows)} segment/time-set rows: {output.resolve()}")
            print(f"Raw TomTom result: {raw_output.resolve()}")
            print("These are month-aggregated speed/travel-time statistics, not daily observations or vehicle counts.")
            return 0
        if state in {"ERROR", "REJECTED", "CANCELLED", "EXPIRED"}:
            print(f"TomTom job ended in state {state}: {status.get('messages', [])}", file=sys.stderr)
            return 1
    print(f"Timed out waiting for job {job_id}; check its status in the TomTom MOVE portal.", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zoom", type=int, default=12, choices=range(10, 19))
    parser.add_argument(
        "--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="Optional study-area bounds; defaults to an approximate HCMC-wide bbox.",
    )
    parser.add_argument(
        "--center-only", action="store_true",
        help="Fetch just one tile near central HCMC instead of the default city-wide bbox.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    parser.add_argument(
        "--month", metavar="YYYY-MM",
        help="Request historical Traffic Stats for a full month; requires a MOVE / Traffic Stats key.",
    )
    args = parser.parse_args()

    if args.month:
        output = args.output
        if output == OUTPUT_CSV:
            output = Path(f"etl/data/road_data_tomtom/tomtom_hcmc_historical_traffic_{args.month.replace('-', '_')}.csv")
        return fetch_historical_month(args.month, output)

    if not TOMTOM_API_KEY or TOMTOM_API_KEY == "PASTE_YOUR_TOMTOM_API_KEY_HERE":
        print("Set TOMTOM_API_KEY in your environment or in this script first.", file=sys.stderr)
        return 2

    try:
        import mapbox_vector_tile
    except ImportError:
        print(
            "Missing vector-tile decoder. Run this script with the project's "
            "uv environment: uv run --project etl python scripts/test_tomtom_traffic.py",
            file=sys.stderr,
        )
        return 2

    if args.center_only and args.bbox:
        parser.error("--center-only and --bbox cannot be used together")
    bounds = args.bbox or DEFAULT_HCMC_BBOX
    if args.center_only:
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2
        tiles = [tile_xy(center_lat, center_lon, args.zoom)]
    else:
        tiles = bbox_tiles(*bounds, args.zoom)

    captured_utc = datetime.now(timezone.utc)
    captured_local = captured_utc.astimezone(HCMC_TZ)
    fetched_at = captured_utc.isoformat()
    time_period = hcmc_time_period(captured_local)
    rows: list[dict] = []
    session = requests.Session()
    session.headers.update({"TomTom-Api-Version": "1", "User-Agent": "UrbanDynamics-Traffic-Test/1.0"})

    for x, y in tiles:
        params = {
            "apiVersion": 1,
            "key": TOMTOM_API_KEY,
            "tags": "road_category,road_subcategory,relative_speed,absolute_speed,openlr,road_closure,part_of_two_way_road",
        }
        url = f"{API_URL}/{args.zoom}/{x}/{y}.pbf"
        response = session.get(url, params=params, timeout=30)
        if not response.ok:
            # Avoid printing the request URL because it contains the API key.
            raise SystemExit(f"TomTom request failed: HTTP {response.status_code}; response: {response.text[:500]}")

        decoded = mapbox_vector_tile.decode(
            response.content,
            default_options={"y_coord_down": True},
        )
        layer = decoded.get("Traffic flow") or next(iter(decoded.values()), {})
        for feature in layer.get("features", []):
            props = feature.get("properties", {})
            rows.append({
                "fetched_at_utc": fetched_at,
                "fetched_at_hcmc": captured_local.isoformat(),
                "time_period_hcmc": time_period,
                "tile_zoom": args.zoom,
                "tile_x": x,
                "tile_y": y,
                "road_category": props.get("road_category", ""),
                "road_subcategory": props.get("road_subcategory", ""),
                "current_speed_kmh": props.get("absolute_speed", ""),
                "relative_speed": props.get("relative_speed", ""),
                "road_closure": props.get("road_closure", False),
                "part_of_two_way_road": props.get("part_of_two_way_road", False),
                "openlr": props.get("openlr", ""),
                "geometry_wkt": to_wkt(feature.get("geometry", {}), x, y, args.zoom),
            })
        time.sleep(0.1)  # modest pacing for a multi-tile city snapshot

    args.output.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "fetched_at_utc", "fetched_at_hcmc", "time_period_hcmc",
        "tile_zoom", "tile_x", "tile_y", "road_category",
        "road_subcategory", "current_speed_kmh", "relative_speed", "road_closure",
        "part_of_two_way_road", "openlr", "geometry_wkt",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Fetched {len(tiles)} tile(s), decoded {len(rows)} road-flow features.")
    print(f"Capture time: {captured_local.isoformat()} ({time_period}; Asia/Ho_Chi_Minh)")
    print(f"CSV: {args.output.resolve()}")
    print("Fields include current/free-flow-relative speed and road geometry; no vehicle-count field is provided by this API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
