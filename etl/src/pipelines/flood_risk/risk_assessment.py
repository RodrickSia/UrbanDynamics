import math
from datetime import datetime, timedelta, timezone

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform

from .config import MIN_WET_WINDOWS, PERCENTILE, RADIUS_M


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Rain timestamps must include timezone")
    return result.astimezone(timezone.utc)


def hourly_values(station):
    values = []
    for hour in station["hourly"]:
        rain = float(hour["precipitation_mm"])
        if not math.isfinite(rain) or rain < 0:
            raise ValueError("Rainfall must be finite nonnegative millimeters")
        values.append((timestamp(hour["time"]), rain))
    values.sort()
    if len({t for t, _ in values}) != len(values):
        raise ValueError("Duplicate rainfall timestamps")
    return values


def three_hour_windows(station):
    values = hourly_values(station)
    return [
        (values[i][0], sum(v for _, v in values[i : i + 3]))
        for i in range(len(values) - 2)
        if values[i + 1][0] - values[i][0] == timedelta(hours=1)
        and values[i + 2][0] - values[i + 1][0] == timedelta(hours=1)
    ]


def threshold(history_station, month, issued_at):
    cutoff = timestamp(issued_at)
    # Vietnam's calendar month, not UTC's month at midnight boundaries.
    vietnam = timezone(timedelta(hours=7))
    values = [
        rain
        for start, rain in three_hour_windows(history_station)
        if start.astimezone(vietnam).month == month
        and start + timedelta(hours=3) <= cutoff
        and rain >= 1
    ]
    if len(values) < MIN_WET_WINDOWS:
        return None, len(values)
    return float(np.percentile(values, PERCENTILE)), len(values)


def metric_transforms(point):
    local = CRS.from_proj4(
        f"+proj=aeqd +lat_0={point.y} +lon_0={point.x} +datum=WGS84 +units=m"
    )
    return (
        Transformer.from_crs(4326, local, always_xy=True).transform,
        Transformer.from_crs(local, 4326, always_xy=True).transform,
    )


def evaluate(floods, forecast, history, scenario_mm=None, radius_m=RADIUS_M):
    if not 1 <= radius_m <= 2000:
        raise ValueError("Radius must be between 1 and 2000 meters")
    if scenario_mm is not None and (not math.isfinite(scenario_mm) or scenario_mm < 0):
        raise ValueError("Scenario rainfall must be finite and nonnegative")
    issued_at = forecast["issued_at"]
    issuance = timestamp(issued_at)
    historical = {station["id"]: station for station in history["stations"]}
    prepared = []
    for station in forecast["stations"]:
        point = Point(float(station["longitude"]), float(station["latitude"]))
        if not (-180 <= point.x <= 180 and -90 <= point.y <= 90):
            raise ValueError("Invalid rain station coordinates")
        windows = [
            (start, rain)
            for start, rain in three_hour_windows(station)
            if start >= issuance
            and start + timedelta(hours=3) <= issuance + timedelta(hours=24)
        ]
        if not windows:
            raise ValueError("No contiguous future 3-hour forecast window")
        prepared.append((station, point, windows))
    if not prepared:
        raise ValueError("Forecast stations missing")
    output = []
    threshold_cache = {}
    for feature in floods["features"]:
        point = shape(feature["geometry"])
        if point.geom_type != "Point":
            raise ValueError("Flood risk requires historical Point observations")
        forward, reverse = metric_transforms(point)
        station, station_point, windows = min(
            prepared, key=lambda item: transform(forward, item[1]).distance(Point(0, 0))
        )
        # Alert horizon is the greatest 3h total over the supplied forecast (normally next 24h).
        start, forecast_mm = max(windows, key=lambda item: item[1])
        month = start.astimezone(timezone(timedelta(hours=7))).month
        key = (station["id"], month)
        if key not in threshold_cache:
            threshold_cache[key] = threshold(
                historical.get(station["id"], {"hourly": []}), month, issued_at
            )
        threshold_mm, sample_count = threshold_cache[key]
        rain_mm = forecast_mm if scenario_mm is None else scenario_mm
        status = (
            "insufficient_history"
            if threshold_mm is None
            else "rain_alert_near_historical_flood"
            if rain_mm >= threshold_mm
            else "no_rain_threshold_exceedance"
        )
        ring = transform(reverse, Point(0, 0).buffer(radius_m))
        output.append(
            {
                "type": "Feature",
                "id": str(feature["id"]),
                "geometry": mapping(ring),
                "properties": {
                    "status": status,
                    "rain_3h_mm": rain_mm,
                    "threshold_p90_3h_mm": threshold_mm,
                    "wet_windows": sample_count,
                    "radius_m": radius_m,
                    "station_id": station["id"],
                    "station_distance_m": round(
                        transform(forward, station_point).distance(Point(0, 0)), 1
                    ),
                    "forecast_window_start": start.isoformat(),
                    "issued_at": issued_at,
                    "historical_event_id": feature["id"],
                    "location": feature["properties"].get("location"),
                    "scenario": scenario_mm is not None,
                    "evidence": {
                        "event": feature["properties"],
                        "rain_source": forecast.get("source_url"),
                        "history_source": history.get("source_url"),
                    },
                    "limitations": "Heuristic rainfall indicator; buffer is a search neighborhood, not a flood extent or depth prediction.",
                },
            }
        )
    return output
