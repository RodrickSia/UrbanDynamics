"""Read the generated baseline used by the map; never replace missing data with zero."""
import json
import logging
import math

from psycopg import Error as DatabaseError
from shapely.ops import unary_union
from src.shared.database import connect_to_warehouse, warehouse_configured

from .geometry import projected, geojson, polygonal
from .development import minimum_setback

logger = logging.getLogger(__name__)


def buildings(parcel, study_area):
    if not warehouse_configured():
        return None
    try:
        with connect_to_warehouse() as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            if connection.execute("SELECT to_regclass('buildings.synthetic_residential')").fetchone()[0] is None:
                return None
            if parcel['id'].startswith('zone:'):
                rows = connection.execute('''SELECT ST_AsGeoJSON(geom),height_m,floors,height_source,generator_version
                    FROM buildings.synthetic_residential
                    WHERE ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))''',
                    (json.dumps(parcel['geometry']),)).fetchall()
            else:
                rows = connection.execute('''SELECT ST_AsGeoJSON(geom),height_m,floors,height_source,generator_version
                    FROM buildings.synthetic_residential WHERE parcel_id=%s''', (int(parcel['id']),)).fetchall()
    except (DatabaseError, OSError):
        logger.warning('Generated baseline unavailable for parcel %s', parcel['id'])
        return None
    region = projected(parcel['geometry']).intersection(projected(study_area))
    result = []
    for index, (geometry, height, floors, source, version) in enumerate(rows):
        clipped = projected(json.loads(geometry)).intersection(region)
        if clipped.area > .01:
            result.append({'id': f"generated-{parcel['id']}-{index}", 'geometry': geojson(clipped),
                           'setback_geometry': geojson(projected(json.loads(geometry)).intersection(projected(parcel['geometry']))),
                           'height_m': height, 'floors': floors, 'source': source,
                           'version': version, 'space_use_id': 'residential'})
    # An absent generated row says nothing about Goong/source buildings on the parcel.
    return result or None


def report(parcel, study_area, records):
    if not records:
        return {'status': 'unavailable', 'buildings': [], 'metrics': None}
    region = projected(parcel['geometry']).intersection(projected(study_area))
    area = region.area
    shapes = [projected(b['geometry']).intersection(region) for b in records]
    gfa = sum(g.area*b['floors'] for g, b in zip(shapes, records))
    footprint = unary_union(shapes).area
    source = 'Generated parcel buildings'
    if any(b.get('provider') == 'goong' for b in records):
        source = 'Mapped buildings · Goong loaded tiles · estimated floors/heights'
    return {'status': 'estimated', 'source': source, 'buildings': records,
            'metrics': {'gfa_m2': gfa, 'footprint_m2': footprint, 'far': gfa/area,
                        'coverage_pct': footprint/area*100, 'max_height': max(b['height_m'] for b in records),
                        'max_floors': max(b['floors'] for b in records),
                        'setbacks': minimum_setback(parcel, records)}}


def with_map_buildings(parcel, study_area, records, collection):
    """Supplement canonical generated records with bounded, unverified map context."""
    result = list(records or [])
    region = projected(parcel['geometry']).intersection(projected(study_area))
    occupied = unary_union([projected(b['geometry']) for b in result])
    groups = {}
    for feature in collection.features:
        geometry = feature.geometry.model_dump()
        key = str(feature.id) if feature.id is not None else json.dumps(geometry, sort_keys=True)
        entry = groups.setdefault(key, {'feature': feature, 'parts': []})
        entry['parts'].append(projected(geometry))
    for key, entry in groups.items():
        footprint = polygonal(unary_union(entry['parts']).intersection(region))
        if footprint is None or footprint.intersection(occupied).area > .01:
            continue
        props = entry['feature'].properties
        def number(keys):
            for name in keys:
                try:
                    value = float(props.get(name))
                except (ValueError, TypeError):
                    continue
                if math.isfinite(value) and 0 < value <= 1000:
                    return value
            return None
        height = number(('max_height', 'height', 'render_height', 'building:height'))
        floors = number(('floors', 'building:levels', 'levels'))
        # Same visual fallback as the map, explicitly marked as an estimate.
        height = height or 12.0
        floors = max(1, min(200, round(floors or height / 3.2)))
        result.append({'id': f'goong-{key}', 'geometry': geojson(footprint),
                       'setback_geometry': geojson(unary_union(entry['parts']).intersection(projected(parcel['geometry']))),
                       'height_m': height, 'floors': floors, 'space_use_id': 'other',
                       'provider': 'goong', 'source': 'Loaded Goong tiles; estimated floors/height'})
        occupied = occupied.union(footprint)
    return result or None


def zoning(plan, scenario, parcel):
    area = projected(parcel['geometry']).intersection(projected(plan['study_area']))
    types = {t['id']: t for t in plan['types']}
    rows = []
    for zone in scenario['zones']:
        overlap = projected(zone['geometry']).intersection(area).area
        if overlap > .01:
            kind = types[zone['type_id']]
            rows.append({'zone_id': zone['id'], 'type_id': kind['id'], 'code': kind['code'],
                         'name': kind['name'], 'color': kind['color'], 'percent': overlap/area.area*100})
    return sorted(rows, key=lambda row: -row['percent'])
