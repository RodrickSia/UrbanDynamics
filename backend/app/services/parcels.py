"""Indexed parcel geometry and explicitly indicative road-price associations."""
import json
import math
import re
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from src.shared.database import connect_to_warehouse
from src.pipelines.parcels_hcmc import config as parcel_config
from app.services.parcel_classification import PRICE_CATEGORIES, classify

PALETTE = json.loads(Path(parcel_config.__file__).with_name('land_use_colors.json').read_text(encoding='utf-8'))
COLORS = {code: entry['color'] for code, entry in PALETTE['entries'].items()}
MIN_ZOOM = 12
MAX_NATIVE_ZOOM = 16
UNKNOWN = {'', 'null', 'none', 'nan'}


def land_use(raw):
    code = str(raw or '').strip()
    if code.lower() in UNKNOWN:
        code = None
    entry = PALETTE['entries'].get(code, {})
    return {'code': code, 'label': entry.get('label'),
            'color': entry.get('color', PALETTE['fallback_color']),
            'color_source': 'source_sample' if entry else 'unknown'}


def planning_breakdown(text):
    rows = []
    for part in str(text or '').split(';'):
        match = re.fullmatch(r'\s*(.+?):\s*([\d]+(?:[.,]\d+)?)\s*m[2²]\s*', part)
        if match:
            rows.append({'label': match[1].strip(), 'area_m2': float(match[2].replace(',', '.'))})
    return rows


def positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def price_reference(parcel, candidates):
    classification = classify(parcel.get('mdsdd'))
    if parcel.get('conflicting_land_use'):
        classification.update(normalized_land_use=None, price_category=None,
                              classification_confidence='unmapped')
    result = {'status': 'unavailable', 'method': 'nearby_road_geometry',
              'unit_price_vnd_m2': None, 'estimated_land_total_vnd': None,
              'candidates': candidates, 'selected': None,
              'road_match_status': 'none', 'geometry_review_status': 'unknown',
              'valuation_confidence': 'none', 'provenance': 'Published road-price layer',
              **classification}
    if not classification['price_category']:
        result['status'] = 'unsupported_land_use'
        return result
    # Boundaries near a road are evidence of proximity, not legal frontage.
    nearby = [item for item in candidates if item['distance_m'] <= 15]
    if not nearby:
        return result
    identities = {(item['properties'].get('road'), item['properties'].get('start'),
                   item['properties'].get('end'),
                   tuple(str(item['properties'].get(field)) for field in sorted(PRICE_CATEGORIES.values())))
                  for item in nearby}
    if len(identities) != 1 or len(candidates) >= 9:
        result['status'] = 'ambiguous'
        return result
    selected = nearby[0]
    props = selected['properties']
    result['selected'] = selected
    result['road_match_status'] = str(props.get('match_confidence') or 'unknown')
    result['geometry_review_status'] = 'reviewed' if props.get('geometry_reviewed') is True else 'unreviewed'
    if (props.get('geometry_coverage') == 'whole_named_road_proxy' or
        not (props.get('geometry_reviewed') is True or props.get('match_confidence') == 'spatially_checked')):
        result['status'] = 'unverified'
        return result
    field = PRICE_CATEGORIES[classification['price_category']]
    unit_price = positive(props.get(field))
    if not unit_price:
        return result
    result.update(status='reference', unit_price_vnd_m2=unit_price)
    result['valuation_confidence'] = (
        'low' if classification['classification_confidence'] == 'low' else
        'high' if result['geometry_review_status'] == 'reviewed' and
                  classification['classification_confidence'] == 'high' else 'medium')
    area = positive(parcel.get('area_m2'))
    identity = str(parcel.get('uniq_id') or '').strip().lower()
    if area and identity not in UNKNOWN | {'0'} and math.isfinite(unit_price * area):
        result['estimated_land_total_vnd'] = round(unit_price * area)
    return result


ATTRIBUTES = ('id, uniq_id, tinh, quan, phuong, to_ban_do, thua, mdsdd, '
              'loai_dat_qh, quyet_dinh, do_an, source_fragments, conflicting_land_use, area_m2')


def detail(parcel_id):
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '5s'")
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(f'SELECT {ATTRIBUTES} FROM parcels.plot WHERE id = %s', (parcel_id,))
            parcel = cursor.fetchone()
            if parcel is None:
                return None
            cursor.execute("""
                SELECT f.feature_id, f.properties,
                       ST_Distance(f.geom::geography,p.geom::geography) AS distance_m
                FROM parcels.plot p JOIN public.layer_features f
                  ON f.layer='land_price'
                 AND f.geom && ST_Expand(p.geom,0.0005)
                 AND ST_DWithin(f.geom::geography,p.geom::geography,40)
                WHERE p.id=%s
                ORDER BY distance_m, f.feature_id LIMIT 9
            """, (parcel_id,))
            candidates = cursor.fetchall()
    # Expose only public price provenance, not arbitrary source metadata.
    allowed = {'road', 'start', 'end', 'ward', 'source_url', 'pdf_page', 'effective_from',
               'geometry_reviewed', 'source_values_reviewed', 'match_confidence', 'geometry_coverage',
               *PRICE_CATEGORIES.values()}
    for candidate in candidates:
        candidate['properties'] = {k: v for k, v in candidate['properties'].items() if k in allowed}
        candidate['distance_m'] = round(candidate['distance_m'], 2)
    return {'parcel': parcel, 'land_use': land_use(None if parcel['conflicting_land_use'] else parcel['mdsdd']),
            'area_source': 'map_geometry', 'planning': planning_breakdown(parcel['loai_dat_qh']),
            'price': price_reference(parcel, candidates)}


def vector_tile(z, x, y):
    if z < MIN_ZOOM:
        return b''
    # Canonical fragments are merged at ingestion, never during map requests.
    # Distant views omit polygons below 2 screen pixels; all plots return at z16.
    resolution = 40075016.68557849 / (512 * 2**z)
    min_area = (resolution * 2)**2 if z < 16 else 0
    tolerance = resolution * 0.3 if z < 16 else 0
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '5s'")
        row = connection.execute("""
            WITH bounds AS (SELECT ST_TileEnvelope(%s,%s,%s) AS geom),
            selected AS (
                SELECT p.*, ST_SimplifyPreserveTopology(p.geom_web,%s) AS display_geom
                FROM parcels.plot p, bounds b
                WHERE p.geom_web && ST_Expand(b.geom,(ST_XMax(b.geom)-ST_XMin(b.geom))*64/4096)
                  AND p.area_web >= %s
            ), tile AS (
                SELECT p.id AS feature_id, p.id::text AS parcel_id, p.mdsdd,
                       CASE WHEN p.conflicting_land_use THEN '#94a3b8'
                            ELSE COALESCE(%s::jsonb->>p.mdsdd,'#94a3b8') END AS color,
                       p.to_ban_do, p.thua,
                       ST_AsMVTGeom(p.display_geom,b.geom,4096,64,true) AS geom
                FROM selected p, bounds b
            ) SELECT ST_AsMVT(tile,'features',4096,'geom','feature_id') FROM tile
        """, (z, x, y, tolerance, min_area, Jsonb(COLORS))).fetchone()
    return bytes(row[0]) if row and row[0] else b''


def plan_vector_tile(study_area, z, x, y):
    """Clip parcel polygons to a saved plan before vector-tile encoding."""
    if z < MIN_ZOOM:
        return b''
    resolution = 40075016.68557849 / (512 * 2**z)
    min_area = (resolution * 2)**2 if z < 16 else 0
    tolerance = resolution * 0.3 if z < 16 else 0
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '5s'")
        row = connection.execute("""
            WITH bounds AS (SELECT ST_TileEnvelope(%s,%s,%s) AS geom),
            study AS (SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),3857) AS geom),
            clipped AS (
                SELECT p.id,
                       ST_CollectionExtract(ST_Intersection(
                           ST_SimplifyPreserveTopology(p.geom_web,%s),s.geom),3) AS geom
                FROM parcels.plot p, bounds b, study s
                WHERE p.geom_web && b.geom AND p.geom_web && s.geom
                  AND ST_Intersects(p.geom_web,s.geom) AND p.area_web >= %s
            ), tile AS (
                SELECT p.id AS feature_id,
                       ST_AsMVTGeom(p.geom,b.geom,4096,64,true) AS geom
                FROM clipped p, bounds b WHERE NOT ST_IsEmpty(p.geom)
            ) SELECT ST_AsMVT(tile,'features',4096,'geom','feature_id') FROM tile
        """, (z, x, y, json.dumps(study_area), tolerance, min_area)).fetchone()
    return bytes(row[0]) if row and row[0] else b''
