from src.shared.spatial import read_boundary
from . import extract, transform, load
from .config import MAX_ITEMS
def run(boundary=None, catalog_only=False, limit=MAX_ITEMS, **kwargs):
    if boundary is None:
        raise ValueError("flood_satellite requires --boundary pointing to a WGS84 polygon")
    polygon = read_boundary(boundary)
    return load.run(transform.run(extract.run(polygon, catalog_only, limit), polygon, catalog_only))
