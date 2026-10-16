"""Indexed parcel geometry and explicitly indicative road-price associations."""
import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP
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
MAX_PRICE_DISTANCE_M = 150


def land_use(raw):
    code = str(raw or '').strip()
    if code.lower() in UNKNOWN:
        code = None
    entry = PALETTE['entries'].get(code, {})
    return {'code': code, 'label': entry.get('label'),
            'color': entry.get('color', PALETTE['fallback_color']),
            'color_source': 'parcel_type_palette' if entry else 'unknown'}


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


def planning_residential_reference(parcel):
    """A source L parcel may use a unit-price category from explicit apartment planning."""
    if str(parcel.get('mdsdd') or '').strip().upper() != 'L':
        return False
    rows = planning_breakdown(parcel.get('loai_dat_qh'))
    parts = [part for part in str(parcel.get('loai_dat_qh') or '').split(';') if part.strip()]
    labels = {row['label'].casefold() for row in rows}
    return (len(rows) == len(parts) and
            any(row['label'].casefold() == 'đất chung cư phức hợp' and row['area_m2'] > 0
                for row in rows) and
            labels <= {'đất chung cư phức hợp', 'đất giao thông'})


def price_reference(parcel, candidates):
    classification = classify(parcel.get('mdsdd'))
    classification['classification_basis'] = 'source_land_use' if classification['price_category'] else 'unmapped'
    if parcel.get('conflicting_land_use'):
        classification.update(normalized_land_use=None, price_category=None,
                              classification_confidence='unmapped', classification_basis='unmapped')
    elif not classification['price_category'] and planning_residential_reference(parcel):
        classification.update(normalized_land_use='Planned apartment use',
                              price_category='Residential', classification_confidence='low',
                              classification_basis='planning')
    result = {'status': 'unavailable', 'method': 'nearby_road_geometry',
              'unit_price_vnd_m2': None, 'estimated_land_total_vnd': None,
              'candidates': candidates, 'selected': None,
              'road_match_status': 'none', 'geometry_review_status': 'unknown',
              'valuation_confidence': 'none', 'provenance': 'Published road-price layer',
              **classification}
    if not classification['price_category']:
        result['status'] = 'unsupported_land_use'
        return result
    field = PRICE_CATEGORIES[classification['price_category']]
    # A road centerline can be across a wide street. Use the closest priced
    # segment as a unit-price reference, never infer legal frontage from it.
    priced = sorted((item for item in candidates
                     if item['distance_m'] <= MAX_PRICE_DISTANCE_M
                     and positive(item['properties'].get(field))),
                    key=lambda item: (item['distance_m'], str(item['feature_id'])))
    if not priced:
        return result
    selected = priced[0]
    props = selected['properties']
    result['selected'] = selected
    result['road_match_status'] = str(props.get('match_confidence') or 'unknown')
    result['geometry_review_status'] = 'reviewed' if props.get('geometry_reviewed') is True else 'unreviewed'
    automatic_reference = (
        props.get('match_confidence') == 'automatic_reference'
        and props.get('publication_match_mode') == 'automatic'
        and props.get('price_kind') == 'table_reference'
        and props.get('geometry_coverage') in {'citywide_road_reference', 'actual_road_piece_reference'}
    )
    unit_price = positive(props.get(field))
    close_candidates = [item for item in candidates if item['distance_m'] <= 15]
    identities = {(item['properties'].get('road'), item['properties'].get('start'),
                   item['properties'].get('end'), positive(item['properties'].get(field)))
                  for item in close_candidates}
    verified_geometry = (props.get('geometry_reviewed') is True or
                         props.get('match_confidence') == 'spatially_checked')
    provisional = (not verified_geometry or automatic_reference or
                   props.get('geometry_coverage') == 'whole_named_road_proxy' or
                   classification['classification_basis'] == 'planning' or
                   classification['classification_confidence'] != 'high' or
                   selected['distance_m'] > 15 or len(identities) != 1)
    result.update(status='provisional' if provisional else 'reference',
                  unit_price_vnd_m2=unit_price)
    result['valuation_confidence'] = (
        'low' if provisional or classification['classification_confidence'] == 'low' else
        'high' if result['geometry_review_status'] == 'reviewed' and
                  classification['classification_confidence'] == 'high' else 'medium')
    area = positive(parcel.get('area_m2'))
    # The total is an indicative arithmetic estimate, even for provisional
    # road associations. Planning-only category inference cannot value the
    # whole parcel because its planned uses may cover different subareas.
    if area and classification['classification_basis'] == 'source_land_use':
        total = Decimal(str(area)) * Decimal(str(unit_price))
        result['estimated_land_total_vnd'] = int(total.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
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
                 AND f.geom && ST_Expand(p.geom,0.0015)
                 AND ST_DWithin(f.geom::geography,p.geom::geography,%s)
                WHERE p.id=%s
                ORDER BY distance_m, f.feature_id LIMIT 64
            """, (MAX_PRICE_DISTANCE_M, parcel_id))
            candidates = cursor.fetchall()
    # Expose only public price provenance, not arbitrary source metadata.
    allowed = {'road', 'start', 'end', 'ward', 'source_url', 'pdf_page', 'effective_from',
               'geometry_reviewed', 'source_values_reviewed', 'match_confidence', 'geometry_coverage',
               'publication_match_mode', 'price_kind', 'match_method', 'source_road', 'matched_road_name',
               *PRICE_CATEGORIES.values()}
    for candidate in candidates:
        candidate['properties'] = {k: v for k, v in candidate['properties'].items() if k in allowed}
        candidate['distance_m'] = round(candidate['distance_m'], 2)
    return {'parcel': parcel, 'land_use': land_use(None if parcel['conflicting_land_use'] else parcel['mdsdd']),
            'area_source': 'map_geometry', 'planning': planning_breakdown(parcel['loai_dat_qh']),
            'price': price_reference(parcel, candidates)}


def development_parcel(parcel_id):
    """Full selected geometry only; road valuation never supplies zoning rules."""
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '5s'")
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT id::text AS id, mdsdd AS land_use, "
                           "ST_AsGeoJSON(geom,9)::json AS geometry FROM parcels.plot WHERE id=%s", (parcel_id,))
            return cursor.fetchone()


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
                SELECT p.id, p.mdsdd,
                       CASE WHEN p.conflicting_land_use THEN '#94a3b8'
                            ELSE COALESCE(%s::jsonb->>p.mdsdd,'#94a3b8') END AS color,
                       ST_CollectionExtract(ST_Intersection(
                           ST_SimplifyPreserveTopology(p.geom_web,%s),s.geom),3) AS geom
                FROM parcels.plot p, bounds b, study s
                WHERE p.geom_web && b.geom AND p.geom_web && s.geom
                  AND ST_Intersects(p.geom_web,s.geom) AND p.area_web >= %s
            ), tile AS (
                SELECT p.id AS feature_id, p.id::text AS parcel_id, p.mdsdd, p.color,
                       ST_AsMVTGeom(p.geom,b.geom,4096,64,true) AS geom
                FROM clipped p, bounds b WHERE NOT ST_IsEmpty(p.geom)
            ) SELECT ST_AsMVT(tile,'features',4096,'geom','feature_id') FROM tile
        """, (z, x, y, json.dumps(study_area), Jsonb(COLORS), tolerance, min_area)).fetchone()
    return bytes(row[0]) if row and row[0] else b''


def zoned_parcel_vector_tile(zones, z, x, y):
    """Color only parcel fragments covered by saved proposal zones."""
    if z < MIN_ZOOM or not zones:
        return b''
    resolution = 40075016.68557849 / (512 * 2**z)
    min_area = (resolution * 2)**2 if z < 16 else 0
    tolerance = resolution * 0.3 if z < 16 else 0
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '5s'")
        row = connection.execute("""
            WITH bounds AS (SELECT ST_TileEnvelope(%s,%s,%s) AS geom),
            zone_geometries AS (
                SELECT zone->>'id' AS zone_id,
                       ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON((zone->'geometry')::text),4326),3857) AS geom
                FROM jsonb_array_elements(%s::jsonb) AS entries(zone)
            ), clipped AS (
                SELECT p.id::text AS parcel_id, p.mdsdd, z.zone_id,
                       CASE WHEN p.conflicting_land_use THEN '#94a3b8'
                            ELSE COALESCE(%s::jsonb->>p.mdsdd,'#94a3b8') END AS source_color,
                       ST_CollectionExtract(ST_Intersection(
                           ST_SimplifyPreserveTopology(p.geom_web,%s),z.geom),3) AS geom
                FROM parcels.plot p JOIN zone_geometries z
                  ON p.geom_web && z.geom AND ST_Intersects(p.geom_web,z.geom)
                CROSS JOIN bounds b
                WHERE p.geom_web && ST_Expand(b.geom,(ST_XMax(b.geom)-ST_XMin(b.geom))*64/4096)
                  AND z.geom && ST_Expand(b.geom,(ST_XMax(b.geom)-ST_XMin(b.geom))*64/4096)
                  AND p.area_web >= %s
            ), tile AS (
                SELECT p.parcel_id, p.mdsdd, p.zone_id, p.source_color,
                       ST_AsMVTGeom(p.geom,b.geom,4096,64,true) AS geom
                FROM clipped p, bounds b WHERE NOT ST_IsEmpty(p.geom)
            ) SELECT ST_AsMVT(tile,'features',4096,'geom') FROM tile
        """, (z, x, y, Jsonb(zones), Jsonb(COLORS), tolerance, min_area)).fetchone()
    return bytes(row[0]) if row and row[0] else b''


def study_land_use(study_area):
    """Summarize observed parcel use inside a plan, separately from proposed zoning."""
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '10s'")
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                WITH study AS (
                    SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS geom
                ), clipped AS (
                    SELECT CASE WHEN p.conflicting_land_use THEN NULL
                                ELSE NULLIF(BTRIM(p.mdsdd),'') END AS code,
                           ST_Area(ST_Transform(ST_Intersection(p.geom,s.geom),32648)) AS area_m2
                    FROM parcels.plot p, study s
                    WHERE p.geom && s.geom AND ST_Intersects(p.geom,s.geom)
                )
                SELECT code, count(*) AS parcels, sum(area_m2) AS area_m2
                FROM clipped WHERE area_m2 > 0
                GROUP BY code ORDER BY area_m2 DESC
            """, (json.dumps(study_area),))
            records = cursor.fetchall()
    return {'basis': 'observed_parcels', 'rows': [
        {'code': row['code'], 'parcels': row['parcels'], 'area_m2': round(row['area_m2'], 2),
         'category': PALETTE['entries'].get(row['code'], {}).get('category'),
         'color': land_use(row['code'])['color']}
        for row in records
    ]}
