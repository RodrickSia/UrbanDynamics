import math

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union
from shapely.validation import explain_validity

TO_METERS = Transformer.from_crs(4326, 32648, always_xy=True).transform
TO_WGS84 = Transformer.from_crs(32648, 4326, always_xy=True).transform
EPSILON = 0.01  # square metres; numerical boundary noise only


def projected(value: dict, *, line: bool = False):
    if not isinstance(value, dict) or value.get("type") not in (
        ("LineString",) if line else ("Polygon", "MultiPolygon")
    ):
        raise ValueError("A GeoJSON line is required" if line else "A GeoJSON polygon is required")
    count = 0

    def coordinates(items, depth=0):
        nonlocal count
        if depth > 4:
            raise ValueError("Invalid coordinate nesting")
        if not isinstance(items, (list, tuple)) or not items:
            raise ValueError("Geometry coordinates are missing")
        if isinstance(items[0], (int, float)):
            count += 1
            if len(items) != 2 or any(isinstance(v, bool) or not isinstance(v, (float, int))
                                      or not math.isfinite(v) for v in items):
                raise ValueError("Use finite 2D coordinates")
            if not (106.2 <= items[0] <= 107.2 and 10.3 <= items[1] <= 11.3):
                raise ValueError("Choose a study area in the HCMC pilot region")
        else:
            for item in items:
                coordinates(item, depth + 1)

    coordinates(value.get("coordinates"))
    if count > 2000:
        raise ValueError("Geometry exceeds the 2,000-vertex limit")
    if not line:
        polygons = [value["coordinates"]] if value["type"] == "Polygon" else value["coordinates"]
        if any(len(ring) < 4 or ring[0] != ring[-1] for rings in polygons for ring in rings):
            raise ValueError("Polygon rings must be closed and contain at least three vertices")
    geom = shape(value)
    if geom.is_empty or not geom.is_valid or (line and not geom.is_simple):
        raise ValueError(f"Invalid geometry: {explain_validity(geom)}")
    return transform(TO_METERS, geom)


def polygonal(geom):
    if geom.is_empty:
        return None
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom if geom.area > EPSILON else None
    parts = [p for p in getattr(geom, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    return polygonal(unary_union(parts)) if parts else None


def geojson(geom):
    return mapping(transform(TO_WGS84, geom))


def study_geometry(value):
    geom = projected(value)
    if not 10 <= geom.area <= 25_000_000:
        raise ValueError("Study area must be between 10 m² and 25 km²")
    return geom


def zone_record(geom, type_id, identifier, revision):
    geometry = geojson(geom)
    projected(geometry)  # Enforce the same complexity and validity limits after clipping/union.
    return {"id": identifier, "type_id": type_id, "geometry": geometry,
            "label_point": geojson(geom.representative_point())["coordinates"],
            "area_m2": geom.area, "revision": revision, "source": "Scenario proposal"}
