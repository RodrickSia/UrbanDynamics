import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape, LineString, Point
from shapely.ops import transform
from src.shared.database import warehouse_configured

from ..engine import polygon_and_area
from .library import parameters
from .models import Design
from . import background


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
    resolved = background.resolve(request, site, area, forward, backward)
    nearby = transform(backward, transform(forward, site).buffer(1000))
    directory = Path(os.getenv("DATA_DIR", "data"))
    layers = {}
    for name in ("flood_history", "flood_risk", "flood_satellite", "land_price"):
        path = directory / "layers" / f"{name}.geojson"
        published = (resolved["snapshot"] or {}).get("layers", {}).get(name)
        if published is not None:
            document = published
            raw = background.canonical(document)
            source_status = "published_snapshot_context"
        elif warehouse_configured():
            from app.repository import features as read_features, LayerUnavailable
            try:
                document = read_features(name, bounds=nearby.bounds, limit=10000)
            except LayerUnavailable:
                layers[name] = {"status": "unavailable", "features": []}
                continue
            raw = json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
            source_status = "postgis_context"
        elif not path.exists():
            cached = (resolved["snapshot"] or {}).get("layers", {}).get(name)
            if not cached:
                layers[name] = {"status": "unavailable", "features": []}
                continue
            document = cached
            raw = background.canonical(document)
            source_status = "published_snapshot_context"
        else:
            raw = path.read_bytes()
            document = json.loads(raw)
            source_status = "cached_context"
        features = [f for f in document.get("features", []) if f.get("geometry") and
                    shape(f["geometry"]).intersects(nearby)]
        # A nearby road price does not establish the price applicable to the site.
        layers[name] = {"status": source_status, "metadata": document.get("metadata", {}),
                        "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                        "hash_scope": "published document" if source_status == "published_snapshot_context" else "returned warehouse context" if source_status == "postgis_context" else "cached file bytes",
                        "features": features[:100], "matched_count": len(features),
                        "truncated": len(features) > 100 or document.get("metadata", {}).get("truncated", False), "scope": "within 1 km; not parcel applicability"}
    library = parameters(request.conditions.level, request.conditions.coefficient_profile)
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
    elif resolved["baseline"] is not None:
        baseline = resolved["baseline"]
        baseline_source = resolved["baseline_provenance"]
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
    if resolved["osm"]:
        road_features = []
        for item in resolved["osm"].get("elements", []):
            if item["type"] != "way" or not item.get("tags", {}).get("highway"):
                continue
            coordinates = [(p["lon"], p["lat"]) for p in item.get("geometry", [])]
            if len(coordinates) < 2:
                continue
            clipped = LineString(coordinates).intersection(nearby)
            if not clipped.is_empty and clipped.geom_type in ("LineString", "MultiLineString"):
                road_features.append({"type": "Feature", "geometry": mapping(clipped),
                                      "properties": {"osm_id": item["id"], "kind": "osm_source", **item["tags"]}})
    services = []
    for i, x in enumerate((-150, 200)):
        services.append({"type": "Feature", "geometry": mapping(transform(backward, Point(cx+x, cy))),
                         "properties": {"name": f"Synthetic service {i+1}", "kind": "synthetic",
                                        "capacity": 750, "existing_users": 600,
                                        "network_distance_m": abs(x)+100}})
    population = resolved["population"]
    background_population = 1200
    population_provenance = {"kind": "synthetic", "source": "Pilot default, 1,200 people"}
    if population:
        stats = population.get("statistics", {})
        value = stats.get("population_sum")
        if value is not None and value >= 0 and stats.get("pixel_count", 0) > 0:
            background_population = value
            population_provenance = {"kind": "worldpop_estimate", "source": population,
                                     "limitations": "Population model for snapshot bbox, not measured parcel occupancy or exact 1 km buffer"}
            # A transparent population-derived prior. No claim of traffic calibration.
            modal_vehicles = library["car_person_share"]/library["car_occupancy"]+library["motorcycle_person_share"]/library["motorcycle_occupancy"]
            library["background_vehicles_hour"] = round(background_population*2*max(library["profiles"]["residential"])*modal_vehicles*.5*library["scenario_load_factor"])
            library["existing_service_users"] = background_population*.25
            library["parameter_provenance"]["background_vehicles_hour"] = {
                "kind": "population_based_estimate", "source": population_provenance,
                "formula": "population_bbox * 2 trips/person/day * max(residential_profile) * modal_vehicle_factor * 0.5 internal/boundary participation * stress_factor",
                "assumptions": "Trip rate, profile, mode shares and participation are synthetic; camera counts not yet integrated"}
    service_provenance = {"kind": "synthetic", "capacity_kind": "synthetic", "walk_speed_m_min": 80}
    if resolved["services"] is not None:
        from .road_network import walking_distance
        services = []
        for feature in resolved["services"]:
            point = shape(feature["geometry"])
            if not nearby.covers(point):
                continue
            feature = json.loads(json.dumps(feature))
            feature["properties"]["capacity"] = None
            feature["properties"]["capacity_kind"] = "unknown"
            feature["properties"]["network_distance_m"] = walking_distance(
                resolved["osm"], (site.centroid.x, site.centroid.y), (point.x, point.y), forward)
            services.append(feature)
        service_provenance = {"kind": "osm_locations", "capacity_kind": "synthetic_scenario_total_not_facility_capacity",
                              "walk_speed_m_min": 80, "walking_method": "OSM graph plus assumed straight access connectors; no travel-time SUMO feedback",
                              "limitations": "OSM completeness unknown. No facility capacity or enrollment observed; demand fraction 0.25 remains synthetic. Schools and medical services not interchangeable; combined capacity is a demonstration scenario only."}
    context = {"created_at": datetime.now(timezone.utc).isoformat(), "site_area_m2": area,
               "baseline": baseline, "baseline_provenance": baseline_source,
               "library": library, "conditions": request.conditions.model_dump(mode="json"),
               "layers": layers, "weather_context": weather_context, "roads": road_features,
               "services": services, "background_population": background_population,
               "population_provenance": population_provenance, "service_provenance": service_provenance,
               "data_inventory": resolved["inventory"], "source_osm": resolved["osm"],
               "surrounding_buildings": resolved["surrounding_buildings"],
               "site_center": [site.centroid.x, site.centroid.y],
               "traffic_network_kind": "osm" if resolved["osm"] else "synthetic",
               "seed": request.conditions.seed, "traffic_departure_jitter": rng.random(),
               "planning": {"status": "unavailable", "goals_are_regulations": False},
               "synthetic_components": ["baseline (unless supplied)", "traffic graph and OD", "sewer network/elevations",
                                        "service capacities", "population outside parcel", "utility capacities", "library/costs/goals"]}
    if resolved["osm"]:
        context["synthetic_components"] = ["unmapped baseline surfaces and unknown occupancy", "traffic OD/mode shares/behaviour and gate connector",
                                           "sewer network/elevations", "service capacities", "utility capacities", "library/costs/goals"]
        context["data_inventory"]["baseline_override"] = bool(request.baseline)
    if request.map_context:
        context["synthetic_components"] = [x for x in context["synthetic_components"] if x != "baseline (unless supplied)"]
        context["synthetic_components"].extend(["unmapped baseline surfaces and unknown occupancy", "missing source building heights/floors"])
        context["data_inventory"]["baseline_override"] = bool(request.baseline)
    from .parameter_catalog import catalog
    context["demand_parameter_catalog"] = catalog(library)
    if population_provenance["kind"] == "worldpop_estimate":
        context["synthetic_components"] = [x for x in context["synthetic_components"] if x != "population outside parcel"]
    context["sha256"] = digest({k: v for k, v in context.items() if k != "created_at"})
    return context
