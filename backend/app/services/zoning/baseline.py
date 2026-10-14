"""Read the generated baseline used by the map; never replace missing data with zero."""
import json
import logging

from psycopg import Error as DatabaseError
from shapely.ops import unary_union
from src.shared.database import connect_to_warehouse, warehouse_configured

from .geometry import projected, geojson

logger = logging.getLogger(__name__)


def buildings(parcel, study_area):
    if not warehouse_configured():
        return None
    try:
        with connect_to_warehouse() as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            if connection.execute("SELECT to_regclass('buildings.synthetic_residential')").fetchone()[0] is None:
                return None
            rows = connection.execute('''SELECT ST_AsGeoJSON(geom),height_m,floors,height_source,generator_version
                FROM buildings.synthetic_residential WHERE parcel_id=%s''', (int(parcel['id']),)).fetchall()
    except (DatabaseError, OSError):
        logger.warning('Generated baseline unavailable for parcel %s', parcel['id'])
        return None
    region = projected(parcel['geometry']).intersection(projected(study_area))
    result = []
    for geometry, height, floors, source, version in rows:
        clipped = projected(json.loads(geometry)).intersection(region)
        if clipped.area > .01:
            result.append({'id': f"generated-{parcel['id']}", 'geometry': geojson(clipped),
                           'height_m': height, 'floors': floors, 'source': source,
                           'version': version, 'space_use_id': 'residential'})
    # An absent generated row says nothing about Goong/source buildings on the parcel.
    return result or None


def report(parcel, study_area, records):
    if not records:
        return {'status': 'unavailable', 'buildings': [], 'metrics': None}
    area = projected(parcel['geometry']).intersection(projected(study_area)).area
    shapes = [projected(b['geometry']) for b in records]
    gfa = sum(g.area*b['floors'] for g, b in zip(shapes, records))
    footprint = unary_union(shapes).area
    return {'status': 'estimated', 'source': 'Generated parcel buildings', 'buildings': records,
            'metrics': {'gfa_m2': gfa, 'footprint_m2': footprint, 'far': gfa/area,
                        'coverage_pct': footprint/area*100, 'max_height': max(b['height_m'] for b in records),
                        'max_floors': max(b['floors'] for b in records)}}


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
