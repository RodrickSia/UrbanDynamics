"""Union shadow geometry on a fixed receiver shared by all alternatives."""
from datetime import date

from shapely.geometry import Polygon, Point, mapping, shape
from shapely.ops import transform, unary_union

from ..integrated.context import projection
from ..integrated.geometry import solar_position, sweep


def polygon_parts(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > 1e-8 else []
    if hasattr(geometry, "geoms"):
        return [part for member in geometry.geoms for part in polygon_parts(member)]
    return []


def fixed_context(study):
    """Common sourced off-site objects; attributes/defaults remain explicit."""
    if study.data_mode != "demo_system":
        return {"type": "FeatureCollection", "features": []}
    from .system_demo import load
    from ..integrated.background import osm_features, numeric_tag
    from ..integrated.map_context import surroundings
    document = load(study.system_snapshot_id)
    region = shape(study.study_area.model_dump())
    forward, backward = projection(region)
    registered = unary_union([shape(p.site.model_dump()) for p in study.projects])
    buildings, _, _ = osm_features(document.get("osm", {}))
    collection = surroundings(registered, buildings, forward, backward)
    area = transform(forward, registered).buffer(300)
    for element in sorted(document.get("osm", {}).get("elements", []), key=lambda x:(x["type"],x["id"])):
        if element["type"] != "node" or element.get("tags", {}).get("natural") != "tree":
            continue
        point = Point(element["lon"], element["lat"])
        if registered.covers(point) or not area.covers(transform(forward, point)):
            continue
        height, height_kind = numeric_tag(element["tags"], "height", 6, 50)
        diameter, diameter_kind = numeric_tag(element["tags"], "diameter_crown", 6, 60)
        collection["features"].append({"type": "Feature", "geometry": mapping(point), "properties": {
            "kind": "fixed_surrounding_tree", "height_m": height, "canopy_radius_m": diameter/2,
            "provenance": {"provider": "osm", "source_id": str(element["id"]),
                "height": height_kind, "canopy_diameter": diameter_kind, "survey_verified": False}}})
    if len(collection["features"]) > 500:
        raise ValueError("Solar context exceeds 500 objects; choose a smaller pilot area")
    return collection


def shadows(study, parcels, context_objects=None):
    region = shape(study.study_area.model_dump())
    forward, backward = projection(region)
    area = transform(forward, region)
    registered = unary_union([transform(forward, shape(p.site.model_dump())) for p in study.projects])
    # Fixed comparable receptor excludes every possible building footprint.
    # Changing the chosen footprint must not change the denominator silently.
    roofs = unary_union([transform(forward, shape(b.footprint.model_dump()))
                         for p in study.projects for d in (p.baseline, p.development) for b in d.buildings])
    fixed = context_objects if context_objects is not None else fixed_context(study)
    fixed_roofs = [transform(forward, shape(f["geometry"])) for f in fixed["features"] if f["geometry"]["type"] != "Point"]
    receiver = area.difference(unary_union([roofs]+fixed_roofs))
    inside_receiver = receiver.intersection(registered)
    projects = {p.id: p for p in study.projects}
    objects = []
    for feature in fixed["features"]:
        geometry = transform(forward, shape(feature["geometry"]))
        if geometry.geom_type == "Point":
            geometry = geometry.buffer(feature["properties"]["canopy_radius_m"])
        objects.append((geometry, feature["properties"]["height_m"]))
    for parcel in parcels:
        project = projects[parcel["id"]]
        design = project.development if parcel["active"] else project.baseline
        objects += [(transform(forward, shape(b.footprint.model_dump())), b.height_m) for b in design.buildings]
        objects += [(transform(forward, Point(t.longitude, t.latitude)).buffer(t.canopy_radius_m), t.height_m) for t in design.trees]
    center = region.centroid
    rows, features = [], []
    for hour in range(8, 18):
        east, north, up = solar_position(date.fromisoformat(study.conditions.solar_date), hour, center.y, center.x)
        shadow = unary_union([sweep(p, -height*east/up, -height*north/up) for p, height in objects]).intersection(receiver) if up > .01 and objects else Polygon()
        # Overlay boundaries can produce zero-area lines in GeometryCollection.
        # Publish polygonal shadows for map consumers while preserving area.
        shadow = unary_union(polygon_parts(shadow))
        inside = shadow.intersection(inside_receiver)
        rows.append({"hour_local": hour, "shaded_receiver_m2": shadow.area,
                     "shaded_registered_receiver_m2": inside.area, "shaded_neighbour_receiver_m2": shadow.difference(registered).area})
        if hour in (9, 12, 15) and not shadow.is_empty:
            features.append({"type": "Feature", "geometry": mapping(transform(backward, shadow)),
                             "properties": {"hour_local": hour, "unit": "m2", "source_kind": "synthetic",
                                            "method": "union_solar_geometry", "time_window": study.conditions.solar_date,
                                            "spatial_scope": "fixed_study_outdoor_receiver"}})
    return {"source_kind": "mixed_sourced_inputs" if study.data_mode == "demo_system" else "synthetic", "engine": "solar-geometry-union-2", "hourly": rows,
            "fixed_context_object_count": len(fixed["features"]), "fixed_context": fixed,
            "receiver_area_m2": receiver.area, "registered_receiver_area_m2": inside_receiver.area,
            "metrics": {"mean_shaded_receiver_m2": sum(r["shaded_receiver_m2"] for r in rows)/len(rows),
                        "mean_shaded_neighbour_m2": sum(r["shaded_neighbour_receiver_m2"] for r in rows)/len(rows)},
            "map": {"type": "FeatureCollection", "features": features},
            "limitations": "Fixed receiver excludes all possible project roofs and fixed off-site roofs; flat ground and opaque tree crowns. OSM inventory within 300 m of registered parcels is incomplete; missing height/floors/crowns use labelled defaults. Objects beyond that extract are not modeled. Shade is not temperature, thermal comfort or loss of sunlight to windows." if study.data_mode == "demo_system" else "Fixed receiver excludes union of all possible footprints; flat ground and opaque trees; no context buildings beyond declared parcels. Shade is not temperature, thermal comfort or loss of sunlight to windows."}
