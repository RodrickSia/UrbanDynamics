"""Normalize client map buildings. Source attributes are not surveyed observations."""
import hashlib
import math

from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union


def positive(properties, keys, maximum):
    for key in keys:
        value = properties.get(key)
        if isinstance(value, bool):
            continue
        try:
            value = float(str(value).strip().removesuffix("m").strip())
            if math.isfinite(value) and 0 < value <= maximum:
                return value, key
        except (TypeError, ValueError):
            pass
    return None, None


def normalize(context, site):
    if not box(*context.bbox).covers(site):
        raise ValueError("Map context bbox must cover the selected site")
    groups = {}
    for feature in context.buildings.features:
        polygon = shape(feature.geometry.model_dump())
        properties = feature.properties
        identifier = feature.id
        if identifier is None:
            identifier = properties.get("id")
        key = ("id", str(identifier)) if identifier is not None else ("geometry", polygon.normalize().wkb_hex)
        height, height_key = positive(properties, ("max_height", "height", "render_height", "building:height"), 400)
        if feature.height_kind != "source_attribute":
            height, height_key = None, None
        floors, floor_key = positive(properties, ("building:levels", "levels", "floors"), 100)
        if floors is not None and not floors.is_integer():
            floors, floor_key = None, None
        item = groups.setdefault(key, {"parts": [], "attributes": [], "source_id": str(identifier) if identifier is not None else hashlib.sha256(polygon.normalize().wkb).hexdigest()[:24]})
        item["parts"].append(polygon)
        item["attributes"].append((properties, height, height_key, floors, floor_key))
    features = []
    seen = {}
    for item in groups.values():
        attributes = item["attributes"]
        heights = {x[1] for x in attributes if x[1] is not None}
        floors_set = {x[3] for x in attributes if x[3] is not None}
        if len(heights) > 1 or len(floors_set) > 1:
            raise ValueError("Conflicting source height/floors for the same map building ID")
        selected = max(attributes, key=lambda x: (x[1] is not None, x[3] is not None))
        properties, height, height_key, _, _ = selected
        floor_record = next((x for x in attributes if x[3] is not None), None)
        floors = int(floor_record[3]) if floor_record else max(1, min(100, round(height/3))) if height else 1
        floor_kind = "source_attribute_estimate" if floor_record else "inferred_from_height_3m_per_floor" if height else "synthetic_default"
        used_height = height if height is not None else floors*3
        height_kind = "source_attribute_estimate" if height is not None else "inferred_from_source_floors_3m" if floor_record else "synthetic_default"
        polygon = unary_union(item["parts"])
        key = polygon.normalize().wkb_hex
        if key in seen:
            previous = seen[key]
            old = previous["properties"]
            if old["_provenance"]["height"] == height_kind == "source_attribute_estimate" and old["height"] != used_height:
                raise ValueError("Conflicting source heights for duplicate map geometry")
            if old["_provenance"]["floors"] == floor_kind == "source_attribute_estimate" and old["building:levels"] != floors:
                raise ValueError("Conflicting source floors for duplicate map geometry")
            if height is not None and old["_provenance"]["height"] != "source_attribute_estimate":
                old["height"] = used_height
                old["_provenance"].update(height=height_kind, height_attribute=height_key)
                if old["_provenance"]["floors"] != "source_attribute_estimate":
                    old["building:levels"] = floors
                    old["_provenance"]["floors"] = floor_kind
            if floor_record and old["_provenance"]["floors"] != "source_attribute_estimate":
                old["building:levels"] = floors
                old["_provenance"]["floors"] = floor_kind
                if old["_provenance"]["height"] != "source_attribute_estimate":
                    old["height"] = floors*3
                    old["_provenance"]["height"] = "inferred_from_source_floors_3m"
            continue
        tag = str(properties.get("use") or properties.get("building") or properties.get("amenity") or "other")
        use = {"apartments": "residential", "house": "residential", "detached": "residential",
               "residential": "residential", "school": "school", "office": "office", "hospital": "hospital"}.get(tag, "other")
        provenance = {"provider": context.provider, "source_layer": context.source_layer,
                      "source_id": item["source_id"], "footprint": "client_map_source_clipped",
                      "height": height_kind, "height_attribute": height_key, "floors": floor_kind,
                      "use": "source_tag_or_other", "occupancy": "unknown_assumed_zero", "survey_verified": False}
        feature = {"type": "Feature", "geometry": mapping(polygon), "properties": {
            "source_id": item["source_id"], "name": str(properties.get("name") or f"Map {item['source_id']}")[:80],
            "height": used_height, "building:levels": floors, "use": use, "_provenance": provenance}}
        features.append(feature)
        seen[key] = feature
    metadata = {"provider": context.provider, "source_layer": context.source_layer,
                "dataset_version": context.dataset_version, "captured_at": context.captured_at.isoformat(),
                "bbox": list(context.bbox), "coverage": context.coverage, "coverage_complete": False,
                "input_features": len(context.buildings.features), "normalized_buildings": len(features),
                "source_height_buildings": sum(f["properties"]["_provenance"]["height"] == "source_attribute_estimate" for f in features),
                "height_assumption_buildings": sum(f["properties"]["_provenance"]["height"] != "source_attribute_estimate" for f in features),
                "kind": "client_provided_unverified_source_attributes"}
    return features, metadata


def surroundings(site, features, forward, backward):
    """Fixed buildings outside the redevelopment site; map has priority over OSM."""
    metric_site = transform(forward, site)
    region = metric_site.buffer(300)
    output, occupied = [], []
    for feature in sorted(features, key=lambda f: (0 if f["properties"].get("_provenance") else 1,
                                                   -shape(f["geometry"]).area)):
        original = transform(forward, shape(feature["geometry"]))
        if not original.intersects(region):
            continue
        polygon = original.intersection(region).difference(metric_site)
        if occupied:
            polygon = polygon.difference(unary_union(occupied))
        parts = list(polygon.geoms) if hasattr(polygon, "geoms") else [polygon]
        parts = [p for p in parts if p.geom_type == "Polygon" and p.area >= 2]
        if not parts:
            continue
        polygon = unary_union(parts)
        tags = feature["properties"]
        provenance = tags.get("_provenance")
        if provenance:
            height = tags["height"]
        else:
            from .background import numeric_tag
            floors, floor_kind = numeric_tag(tags, "building:levels", 1, 100)
            height, height_kind = numeric_tag(tags, "height", floors*3, 400)
            provenance = {"provider": "osm", "source_id": str(tags["osm_id"]), "height": height_kind,
                          "floors": floor_kind, "footprint": "osm_clipped", "survey_verified": False}
        output.append({"type": "Feature", "geometry": mapping(transform(backward, polygon)), "properties": {
            "height_m": height, "kind": "fixed_surrounding_building", "provenance": provenance}})
        occupied.append(polygon)
    return {"type": "FeatureCollection", "features": output}
