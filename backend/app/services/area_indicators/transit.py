"""Transit proximity from a versioned local stop snapshot, never basemap labels."""
import json
import math
import os
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, box
from shapely.ops import transform, unary_union

from ..zoning.geometry import TO_METERS, geojson


@lru_cache(maxsize=2)
def read_snapshot(path, modified):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if document.get('type') != 'FeatureCollection' or not document.get('source') or not document.get('captured_at'):
        raise ValueError('Transit snapshot requires source and captured_at')
    bounds = document.get('bbox')
    if (not isinstance(bounds, list) or len(bounds) != 4
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds)
            or not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90)):
        raise ValueError('Transit snapshot requires coverage bounds')
    if len(document.get('features', [])) > 50000:
        raise ValueError('Transit snapshot exceeds 50,000 stops')
    stops = []
    for item in document['features']:
        if item['geometry']['type'] != 'Point':
            raise ValueError('Transit stops must be points')
        point = Point(item['geometry']['coordinates'])
        if not point.is_valid or not (-180 <= point.x <= 180 and -90 <= point.y <= 90):
            raise ValueError('Invalid stop coordinates')
        stops.append((item, transform(TO_METERS, point)))
    return document, stops


def proximity(area, radius):
    default = Path(os.getenv('DATA_DIR', 'data'))/'transit/stops.geojson'
    path = Path(os.getenv('INDICATORS_TRANSIT_PATH', str(default)))
    if not path.is_file():
        return {'status': 'missing', 'coverage_percent': None, 'stops': [], 'geometry': None,
                'reason': 'No transit stop snapshot loaded'}
    document, stops = read_snapshot(str(path), path.stat().st_mtime_ns)
    bounds = transform(TO_METERS, box(*document['bbox']))
    complete = bounds.covers(area.buffer(radius))
    nearby = [(item, point) for item, point in stops if area.distance(point) <= radius]
    covered = unary_union([point.buffer(radius) for _, point in nearby]).intersection(area)
    return {'status': 'proxy' if complete else 'partial',
            'coverage_percent': covered.area/area.area*100 if complete else None,
            'mapped_coverage_percent': covered.area/area.area*100,
            'stop_count': len(nearby), 'radius_m': radius,
            'source': document['source'], 'captured_at': document['captured_at'],
            'method': 'Straight-line area proximity; not walking routes or service frequency',
            'stops': [{'type': 'Feature', 'geometry': item['geometry'],
                       'properties': {'name': item.get('properties', {}).get('name', 'Transit stop')}} for item, _ in nearby],
            'geometry': geojson(covered) if not covered.is_empty else None}
