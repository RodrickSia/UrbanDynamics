"""Geographic validation shared by Khoi's pipelines."""
from pathlib import Path
import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely import force_2d
from .data_io import read_json


def read_boundary(path):
    document = read_json(path)
    geometries = ([f["geometry"] for f in document["features"]]
                  if document.get("type") == "FeatureCollection"
                  else [document["geometry"]] if document.get("type") == "Feature"
                  else [document])
    boundary = force_2d(unary_union([shape(g) for g in geometries]))
    if boundary.geom_type not in ("Polygon", "MultiPolygon") or boundary.is_empty or not boundary.is_valid:
        raise ValueError("Boundary must be a valid nonempty WGS84 polygon")
    if not (-180 <= boundary.bounds[0] < boundary.bounds[2] <= 180
            and -90 <= boundary.bounds[1] < boundary.bounds[3] <= 90):
        raise ValueError("Boundary coordinates must be WGS84 longitude/latitude")
    return boundary


def geographic_frame(path, layer=None):
    frame = gpd.read_file(Path(path), layer=layer)
    if frame.crs is None:
        raise ValueError("Source CRS missing; do not guess coordinates")
    frame = frame.to_crs(4326)
    frame.geometry = frame.geometry.apply(force_2d)
    if frame.geometry.isna().any() or frame.geometry.is_empty.any() or not frame.geometry.is_valid.all():
        raise ValueError("Source has missing, empty or invalid geometry")
    return frame
