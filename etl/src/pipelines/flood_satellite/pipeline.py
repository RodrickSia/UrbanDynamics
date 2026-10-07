from src.shared.spatial import read_boundary

from . import extract, load, transform
from .config import MAX_ITEMS


def run(boundary=None, catalog_only=False, limit=MAX_ITEMS, **kwargs):
    if boundary is None:
        raise ValueError(
            "flood_satellite requires --boundary pointing to a WGS84 polygon"
        )
    polygon = read_boundary(boundary)
    document = transform.run(extract.run(polygon,catalog_only,limit),polygon,catalog_only)
    from src.shared.data_io import read_json
    document['metadata']['scope'] = read_json(boundary).get('metadata',{}).get('scope','Custom boundary-filtered area')
    document['metadata']['lookback_days'] = 30
    return load.run(document)
