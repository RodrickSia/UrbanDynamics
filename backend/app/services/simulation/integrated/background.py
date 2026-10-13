"""Resolve published background data without network calls during prediction.

Snapshots contain team API responses and bounded OSM extracts, not arbitrary
client-provided paths. A source-backed geometry is not a surveyed occupancy.
"""
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Point, Polygon, box, mapping, shape
from shapely.ops import transform, unary_union

from .models import Building, Design
from ..engine import polygon_and_area
from ..models import PolygonInput


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


def snapshot_directory():
    return Path(os.getenv("SIMULATION_SNAPSHOT_DIR", str(Path(os.getenv("DATA_DIR", "data"))/"simulation_snapshots")))


def publish(document, directory=None):
    directory = Path(directory) if directory else snapshot_directory()
    raw = canonical(document)
    identifier = hashlib.sha256(raw).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory/f"{identifier}.json"
    if not path.exists():
        temp = directory/f".{identifier}.tmp"
        temp.write_bytes(raw)
        temp.replace(path)
    return identifier


def load_snapshot(request, site):
    if request.data_mode == "synthetic":
        return None
    directory = snapshot_directory()
    candidates = [directory/f"{request.snapshot_id}.json"] if request.snapshot_id else list(directory.glob("*.json"))
    matches = []
    for path in candidates:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != path.stem:
            raise ValueError("Simulation snapshot integrity check failed")
        document = json.loads(raw)
        bounds = document.get("bbox", [])
        if len(bounds) != 4 or not all(math.isfinite(x) for x in bounds):
            raise ValueError("Invalid simulation snapshot bounds")
        if document.get("schema_version") != 1:
            raise ValueError("Unsupported simulation snapshot schema")
        if box(*bounds).covers(site):
            matches.append((document.get("captured_at", ""), path.stem, document))
    if not matches:
        if request.snapshot_id or request.data_mode == "snapshot_required":
            raise ValueError("No verified simulation snapshot covers the selected site")
        return None
    _, identifier, document = max(matches, key=lambda item: (item[0], item[1]))
    return {**document, "snapshot_id": identifier}


def osm_features(document):
    buildings, surfaces, services = [], [], []
    seen_services = set()
    for item in document.get("elements", []):
        tags = item.get("tags", {})
        coords = [(p["lon"], p["lat"]) for p in item.get("geometry", [])]
        polygon = None
        if len(coords) >= 4 and coords[0] == coords[-1]:
            candidate = Polygon(coords)
            if candidate.is_valid and not candidate.is_empty:
                polygon = candidate
        properties = {**tags, "osm_id": item["id"], "osm_type": item["type"], "kind": "osm_source"}
        if polygon is not None and tags.get("building") not in (None, "no"):
            buildings.append({"type": "Feature", "geometry": mapping(polygon), "properties": properties})
        green = tags.get("landuse") in ("forest", "grass", "meadow", "village_green", "recreation_ground") or tags.get("leisure") in ("park", "garden") or tags.get("natural") in ("wood", "grassland", "scrub")
        if polygon is not None and green:
            surfaces.append({"type": "Feature", "geometry": mapping(polygon), "properties": {**properties, "surface": "green"}})
        if tags.get("amenity") in ("school", "kindergarten", "college", "university", "hospital", "clinic"):
            point = polygon.representative_point() if polygon is not None else (
                Point(item["lon"], item["lat"]) if "lon" in item else None)
            if point is not None:
                key = (tags.get("name"), round(point.x, 4), round(point.y, 4))
                if key in seen_services:
                    continue
                seen_services.add(key)
                services.append({"type": "Feature", "geometry": mapping(point), "properties": properties})
    return buildings, surfaces, services


def numeric_tag(tags, key, default, maximum):
    try:
        value = float(str(tags.get(key, "")).split(";")[0].replace(" m", ""))
        if math.isfinite(value) and 0 < value <= maximum:
            return value, "osm_tag_estimate"
    except (TypeError, ValueError):
        pass
    return default, "synthetic_default"


def baseline_from_osm(site, area, features, green_features, forward, backward, landcover=None):
    """Clip known footprints. Unmapped surfaces/occupancy remain assumptions."""
    blocks, records, occupied = [], [], []
    metric_site = transform(forward, site)
    for feature in sorted(features, key=lambda f: (0 if f["properties"].get("_provenance") else 1,
                                                   -shape(f["geometry"]).area,
                                                   str(f["properties"].get("source_id", f["properties"].get("osm_id", ""))))):
        clipped = shape(feature["geometry"]).intersection(site)
        if clipped.is_empty:
            continue
        metric = transform(forward, clipped)
        if occupied:
            metric = metric.difference(unary_union(occupied))
        # Avoid floating-point leakage outside the site on inverse projection;
        # split again after inset because a narrow connecting sliver may disappear.
        metric = metric.buffer(-.000001)
        pieces = list(metric.geoms) if metric.geom_type == "MultiPolygon" else [metric]
        for piece in pieces:
            if piece.geom_type != "Polygon" or piece.area < 2:
                continue
            if len(blocks) >= 20:
                raise ValueError("Baseline has more than 20 building parts; choose a smaller pilot site")
            footprint = PolygonInput(**mapping(transform(backward, piece)))
            tags = feature["properties"]
            floors, floors_kind = numeric_tag(tags, "building:levels", 1, 100)
            height, height_kind = numeric_tag(tags, "height", floors*3, 400)
            use = tags.get("use") if tags.get("_provenance") else "residential" if tags.get("building") in ("apartments", "residential", "house", "detached") else "other"
            blocks.append(Building(name=tags.get("name", f"OSM {tags.get('osm_id', '')}" )[:80], use=use,
                                  footprint=footprint, floors=max(1, int(floors)), height_m=height))
            records.append(tags.get("_provenance") or {"osm_id": tags["osm_id"], "provider": "osm",
                            "footprint": "osm_clipped", "floors": floors_kind,
                            "height": height_kind, "occupancy": "unknown_assumed_zero", "use": "osm_tag_or_other"})
            occupied.append(piece)
    roof = sum(polygon_and_area(b.footprint)[1] for b in blocks)
    remaining = max(0, area-roof)
    roof_union = unary_union(occupied)
    greens = [transform(forward, shape(f["geometry"])) for f in green_features]
    satellite_paved = []
    if landcover:
        # Built-up is a surface proxy ONLY after removing known roofs. No invented
        # building footprint is created from a mixed 10 m pixel.
        for f in landcover.get("features", []):
            code = f["properties"]["class_code"]
            projected = transform(forward, shape(f["geometry"]))
            if code in (10, 20, 30, 40, 90, 95, 100):
                greens.append(projected)
            elif code == 50:
                satellite_paved.append(projected)
    known_green = unary_union(greens).intersection(metric_site).difference(roof_union).area if greens else 0
    # Scale planar green area to geodesic site area consistently with footprint area.
    known_green = min(remaining, known_green*area/metric_site.area)
    known_paved = unary_union(satellite_paved).intersection(metric_site).difference(roof_union).difference(unary_union(greens)).area*area/metric_site.area if satellite_paved else 0
    known_paved = min(remaining-known_green, known_paved)
    unknown = max(0, remaining-known_green-known_paved)
    baseline = Design(buildings=blocks, green_m2=known_green+unknown*.4,
                      paved_m2=known_paved+unknown*.5, permeable_m2=unknown*.1)
    provenance = {"kind": "mixed_source_and_assumptions", "source": "Client map and/or OSM snapshot, clipped to site",
                  "buildings": records, "mapped_green_m2": known_green, "built_up_paved_proxy_m2": known_paved,
                  "landcover": landcover.get("metadata") if landcover else None, "unclassified_surface_m2": unknown,
                  "unclassified_surface_split": {"paved": .5, "permeable": .1, "green": .4},
                  "coverage_complete": False,
                  "limitations": "Missing mapped footprints do not mean vacant land. Unclassified surfaces are synthetic. Existing occupancy is unknown and assumed zero; demand changes are incremental scenario estimates, not observed before/after totals."}
    return baseline.model_dump(mode="json"), provenance


def resolve(request, site, area, forward, backward):
    snapshot = load_snapshot(request, site)
    result = {"snapshot": snapshot, "inventory": {}, "baseline": None, "baseline_provenance": None,
              "population": None, "services": None, "osm": None}
    buildings, greens = [], []
    if snapshot:
        result["osm"] = snapshot.get("osm")
        if result["osm"]:
            buildings, greens, services = osm_features(result["osm"])
            result["services"] = services
        result["population"] = snapshot.get("population")
        if result["population"] and result["population"].get("year", 9999) > datetime.now(timezone.utc).year:
            result["population"] = None
        if result["population"]:
            value = result["population"].get("statistics", {}).get("population_sum")
            if value is None or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid population statistics in simulation snapshot")
            if result["population"].get("bbox") != snapshot["bbox"]:
                raise ValueError("Population statistics do not match snapshot bounding box")
        result["inventory"] = {"snapshot_id": snapshot["snapshot_id"], "captured_at": snapshot["captured_at"],
                               "bbox": snapshot["bbox"], "sources": snapshot.get("sources", {}),
                               "parcel_count": len(snapshot.get("parcels", {}).get("features", [])),
                               "parcel_truncated": snapshot.get("parcels", {}).get("metadata", {}).get("truncated", False)}
    # Team warehouse is reused directly when configured. A DB failure must surface,
    # rather than silently swapping to a fictional population.
    from src.shared.database import warehouse_configured
    if warehouse_configured() and request.data_mode != "synthetic" and snapshot is None:
        from app import repository
        bounds = tuple(snapshot["bbox"]) if snapshot else transform(backward, transform(forward, site).buffer(1000)).bounds
        years = [y for y in repository.population_years() if y["year"] <= datetime.now(timezone.utc).year]
        if years:
            year = max(years, key=lambda x: x["year"])
            stats = repository.population_statistics(year["year"], bounds)
            if stats and stats["pixel_count"]:
                result["population"] = {"year": year["year"], "bbox": list(bounds), "statistics": stats,
                                        "source": year, "kind": "worldpop_estimate", "scope": "raster pixels in bounding box, not exact buffer or parcel occupancy"}
        try:
            parcels = repository.features("parcels", bounds=site.bounds, limit=1000)
            result["inventory"]["site_parcels"] = {"features": parcels["features"], "metadata": parcels.get("metadata", {})}
        except repository.LayerUnavailable:
            result["inventory"]["site_parcels"] = {"status": "unavailable"}
    elif snapshot:
        result["inventory"]["site_parcels"] = {
            "features": [f for f in snapshot.get("parcels", {}).get("features", []) if f.get("geometry") and shape(f["geometry"]).intersects(site)],
            "metadata": snapshot.get("parcels", {}).get("metadata", {})}
    from .map_context import normalize, surroundings
    inventory = result["inventory"]
    if request.map_context:
        mapped, metadata = normalize(request.map_context, site)
        buildings = mapped + buildings
        inventory["map_context"] = metadata
    if request.baseline is None and (result["osm"] or request.map_context or snapshot and snapshot.get("landcover")):
        result["baseline"], result["baseline_provenance"] = baseline_from_osm(
            site, area, buildings, greens, forward, backward, (snapshot or {}).get("landcover"))
    result["surrounding_buildings"] = surroundings(site, buildings, forward, backward)
    inventory["coverage"] = {
        "roads": "osm_snapshot" if result["osm"] else "synthetic",
        "building_footprints": "client_map_and_osm_incomplete" if request.map_context and result["osm"] else "client_map_incomplete" if request.map_context else "osm_incomplete" if result["osm"] else "unavailable",
        "landcover": "historical_2021" if snapshot and snapshot.get("landcover") else "unavailable",
        "population": "worldpop_estimate" if result["population"] else "synthetic",
        "service_locations": "osm_incomplete" if result["services"] is not None else "synthetic",
        "sewer_network": "synthetic", "utility_spare_capacity": "synthetic", "service_capacity": "synthetic"}
    if result["baseline_provenance"]:
        inventory["baseline_quality"] = {"mapped_building_parts": len(result["baseline"]["buildings"]),
                                         "unclassified_surface_m2": result["baseline_provenance"]["unclassified_surface_m2"],
                                         "existing_occupancy_known": False, "survey_verified": False,
                                         "comparison_basis": "design_scenarios_on_incomplete_estimated_baseline"}
    inventory["warnings"] = ["No local calibration of OD, utility demands or drainage.",
                              "Missing mapped buildings do not establish vacant land; existing occupancy is unknown."]
    if snapshot and snapshot.get("landcover"):
        inventory["warnings"].append("WorldCover 2021 is historical classification, not a 2026 site survey; built-up is only a paved-surface proxy after removing known footprints.")
    if snapshot:
        inventory["warnings"].extend(f"Source acquisition unavailable: {key}" for key in snapshot.get("failures", {}))
    if request.map_context:
        inventory["warnings"].append("Map buildings are client-provided attributes, not a verified complete survey. Visual extrusion defaults are not source heights; missing heights use floors*3 m or 3 m. Site redevelopment replaces on-site baseline buildings; surrounding buildings remain fixed within 300 m.")
    return result
