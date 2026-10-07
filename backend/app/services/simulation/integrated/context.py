import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape, LineString, Point
from shapely.ops import transform

from ..engine import polygon_and_area
from .library import parameters
from .models import Design


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def projection(site):
    center = site.centroid
    crs = CRS.from_proj4(f"+proj=aeqd +lat_0={center.y} +lon_0={center.x} +datum=WGS84 +units=m")
    return (Transformer.from_crs(4326, crs, always_xy=True).transform,
            Transformer.from_crs(crs, 4326, always_xy=True).transform)


def build_context(request):
    site, area = polygon_and_area(request.site)
    if area > 100000:
        raise ValueError("Integrated pilot supports sites up to 100,000 m2")
    forward, backward = projection(site)
    nearby = transform(backward, transform(forward, site).buffer(1000))
    directory = Path(os.getenv("DATA_DIR", "data"))
    layers = {}
    for name in ("flood_history", "flood_risk", "flood_satellite", "land_price"):
        path = directory / "layers" / f"{name}.geojson"
        if not path.exists():
            layers[name] = {"status": "unavailable", "features": []}
            continue
        raw = path.read_bytes()
        document = json.loads(raw)
        features = [f for f in document.get("features", []) if f.get("geometry") and
                    shape(f["geometry"]).intersects(nearby)]
        # A nearby road price does not establish the price applicable to the site.
        layers[name] = {"status": "cached_context", "metadata": document.get("metadata", {}),
                        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                        "features": features[:100], "matched_count": len(features),
                        "truncated": len(features) > 100, "scope": "within 1 km; not parcel applicability"}
    library = parameters(request.conditions.level)
    if request.conditions.rainfall_mm is not None:
        library["rainfall_mm"] = request.conditions.rainfall_mm
        library["rainfall_source"] = "User-defined scenario, not a forecast"
    else:
        library["rainfall_source"] = "Synthetic design event, not a forecast"
    # No automatic use of an expired forecast; persist its timestamp as context only.
    weather = directory / "inputs" / "rainwater_forecast.json"
    weather_context = {"status": "unavailable"}
    if weather.exists():
        raw = weather.read_bytes()
        data = json.loads(raw)
        weather_context = {"status": "cached_not_used_for_design_event", "issued_at": data.get("issued_at"),
                           "source_url": data.get("source_url"), "sha256": hashlib.sha256(raw).hexdigest()}
    if request.baseline:
        baseline = request.baseline.design.model_dump(mode="json")
        baseline_source = {"kind": "user_supplied", "source": request.baseline.source}
    else:
        baseline = Design(paved_m2=area*.15, permeable_m2=area*.15, green_m2=area*.7).model_dump(mode="json")
        baseline_source = {"kind": "synthetic", "source": "Vacant pilot parcel: 15% paved, 15% permeable, 70% green; not surveyed"}
    rng = random.Random(request.conditions.seed)
    # Simple connected scenario graph, placed relative to the site, not inferred sewer/road infrastructure.
    cx, cy = transform(forward, site).centroid.coords[0]
    nodes = {"w": [cx-250, cy], "c": [cx, cy], "e": [cx+250, cy], "g": [cx, cy+100]}
    road_features = [{"type": "Feature", "geometry": mapping(transform(backward, LineString([nodes[a], nodes[b]]))),
                      "properties": {"id": a+b, "kind": "synthetic", "engine": "SUMO"}}
                     for a, b in (("w", "c"), ("c", "e"), ("c", "g"))]
    services = []
    for i, x in enumerate((-150, 200)):
        services.append({"type": "Feature", "geometry": mapping(transform(backward, Point(cx+x, cy))),
                         "properties": {"name": f"Synthetic service {i+1}", "kind": "synthetic",
                                        "capacity": 750, "existing_users": 600,
                                        "network_distance_m": abs(x)+100}})
    context = {"created_at": datetime.now(timezone.utc).isoformat(), "site_area_m2": area,
               "baseline": baseline, "baseline_provenance": baseline_source,
               "library": library, "conditions": request.conditions.model_dump(mode="json"),
               "layers": layers, "weather_context": weather_context, "roads": road_features,
               "services": services, "background_population": 1200,
               "seed": request.conditions.seed, "traffic_departure_jitter": rng.random(),
               "planning": {"status": "unavailable", "goals_are_regulations": False},
               "synthetic_components": ["baseline (unless supplied)", "traffic graph and OD", "sewer network/elevations",
                                        "service capacities", "population outside parcel", "utility capacities", "library/costs/goals"]}
    context["sha256"] = digest({k: v for k, v in context.items() if k != "created_at"})
    return context
