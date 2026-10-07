"""Cached OSM roads and current commune boundaries for spatial price matching."""
import logging
import hashlib
import requests

from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import polygonize_full, unary_union

from src.shared.data_io import data_dir, read_json, session, write_json, file_provenance
from src.shared.spatial import read_boundary
from src.pipelines.flood_history.transform import normalize

ENDPOINTS = ('https://overpass-api.de/api/interpreter',
             'https://overpass.private.coffee/api/interpreter')
LOGGER = logging.getLogger(__name__)


def request(query):
    client = session()
    client.headers['User-Agent'] = ('UrbanDynamics/0.1 '
        '(+https://github.com/RodrickSia/UrbanDynamics; public urban-planning research)')
    last = None
    for endpoint in ENDPOINTS:
        try:
            response = client.post(endpoint, data={'data': query}, timeout=(20, 120))
            response.raise_for_status()
            result = response.json()
            if result.get('remark') or 'elements' not in result:
                raise ValueError('Incomplete Overpass response')
            return result, endpoint
        except (ValueError, requests.RequestException) as error:
            last = error
            LOGGER.warning('OSM source failed: %s (%s, HTTP %s)', endpoint, type(error).__name__,
                           getattr(getattr(error, 'response', None), 'status_code', None))
    raise RuntimeError('OSM sources unavailable; previous published data retained') from last


def ward_name(value):
    key = normalize(value)
    for prefix in ('phuong', 'dac khu', 'dackhu', 'xa'):
        if key.startswith(prefix.replace(' ', '')):
            return key[len(prefix.replace(' ', '')):]
    return key


def relation_polygon(relation):
    parts = {'outer': [], 'inner': []}
    for member in relation.get('members', []):
        role = member.get('role') or 'outer'
        if member.get('type') != 'way' or role not in parts:
            continue
        coordinates = [(p['lon'], p['lat']) for p in member.get('geometry', [])]
        if len(coordinates) < 2:
            raise ValueError('Incomplete boundary way')
        parts[role].append(LineString(coordinates))
    polygons = {}
    for role, lines in parts.items():
        if not lines:
            polygons[role] = None
            continue
        faces, cuts, dangles, invalid = polygonize_full(unary_union(lines))
        if faces.is_empty or any(not g.is_empty for g in (cuts, dangles, invalid)):
            raise ValueError('Boundary rings are not closed')
        polygons[role] = unary_union(list(faces.geoms))
    if polygons['outer'] is None:
        raise ValueError('Missing boundary outer ring')
    result = polygons['outer']
    if polygons['inner'] is not None:
        result = result.difference(polygons['inner'])
    if result.is_empty or not result.is_valid or result.geom_type not in ('Polygon', 'MultiPolygon'):
        raise ValueError('Invalid ward polygon')
    return result


def ward_features(document, city):
    features, rejected = [], []
    for relation in document['elements']:
        tags = relation.get('tags', {})
        # Post-2025 communes use level 6. Old district/city relations and
        # level-8 wards must not silently become the new price-table wards.
        label = tags.get('name:vi') or tags.get('name', '')
        typed = tags.get('designation') in ('ward', 'commune', 'special_zone')
        typed = typed or normalize(label).startswith(('phuong', 'xa', 'dackhu'))
        if tags.get('admin_level') != '6' or not typed:
            continue
        try:
            polygon = relation_polygon(relation)
            overlap = polygon.intersection(city)
            if overlap.area / polygon.area < .95:
                # Con Dao's OSM administrative polygon may include sea while
                # HDX supplies land islands. Verify the known island location.
                island = Point(106.609,8.683)
                if not (ward_name(label)=='condao' and polygon.covers(island) and city.covers(island)):
                    continue
            features.append({'type': 'Feature', 'geometry': mapping(polygon),
                'properties': {'ward_key': ward_name(label), 'name': label,
                    'osm_relation_id': relation['id'], 'admin_level': '6',
                    'source_url': f'https://www.openstreetmap.org/relation/{relation["id"]}',
                    'boundary_kind': 'OSM analytical commune boundary, not a legal cadastral boundary'}})
        except ValueError as error:
            rejected.append({'osm_relation_id': relation['id'], 'reason': str(error)})
    return features, rejected


def wards(boundary, cached=False):
    root = data_dir() / 'raw/land_price/wards'
    catalog = root / 'relations.json'
    city = read_boundary(boundary)
    # Cache geometry batches independently so interrupted requests can resume.
    if not cached or not catalog.exists():
        west, south, east, north = city.bounds
        query = (f'[out:json][timeout:90];rel[boundary=administrative]'
                 f'[admin_level=6]({south},{west},{north},{east});out tags;')
        body, endpoint = request(query)
        body['source_endpoint'] = endpoint
        write_json(catalog, body)
    catalog_data = read_json(catalog)
    price_path = data_dir()/'review/land_price_rows.json'
    wanted = {ward_name(r['ward']) for r in read_json(price_path)['records']} if price_path.exists() else None
    ids = sorted(r['id'] for r in catalog_data['elements']
                 if (normalize(r.get('tags',{}).get('name:vi') or r.get('tags',{}).get('name','')).startswith(('phuong','xa','dackhu')))
                 and (wanted is None or ward_name(r.get('tags',{}).get('name:vi') or r.get('tags',{}).get('name','')) in wanted))
    if not ids:
        raise ValueError('No administrative relations returned')
    # The official OSM read API avoids Overpass geometry slots when that service
    # is overloaded. Sequential requests with independently resumable caches.
    def full(identifier):
        path = root/f'osm-relation-{identifier}.json'
        url = f'https://api.openstreetmap.org/api/0.6/relation/{identifier}/full.json'
        if not cached or not path.exists():
            response = requests.get(url, headers={'User-Agent':
                'UrbanDynamics/0.1 (+https://github.com/RodrickSia/UrbanDynamics)'}, timeout=(20,90))
            response.raise_for_status()
            if len(response.content)>25_000_000:
                raise ValueError('OSM relation response too large')
            write_json(path,response.json())
        body = read_json(path)
        nodes = {e['id']:{'lon':e['lon'],'lat':e['lat']} for e in body['elements'] if e['type']=='node'}
        ways = {e['id']:e for e in body['elements'] if e['type']=='way'}
        relation = next(e for e in body['elements'] if e['type']=='relation' and e['id']==identifier)
        for member in relation['members']:
            if member['type']=='way':
                member['geometry'] = [nodes[n] for n in ways[member['ref']]['nodes']]
        return relation
    elements = []
    for identifier in ids:
        elements.append(full(identifier))
        LOGGER.info('OSM commune boundaries %s/%s', len(elements), len(ids))
    features, rejected = ward_features({'elements': elements}, city)
    if not features:
        raise ValueError('No current, valid HCMC commune polygons')
    document = {'type': 'FeatureCollection', 'features': features, 'metadata': {
        'license': 'ODbL 1.0', 'source_url': catalog_data.get('source_endpoint', ENDPOINTS[0]),
        'catalog_source_time': catalog_data.get('osm3s', {}).get('timestamp_osm_base'),
        'geometry_source_url':'https://api.openstreetmap.org/api/0.6/',
        'boundary_kind': 'OSM analytical boundaries, not legal cadastral boundaries',
        'rejected': rejected, 'provenance': [file_provenance(catalog)]}}
    write_json(data_dir()/'inputs/land_price_wards.geojson', document)
    return document


def road_chunk(bounds, cached=False, depth=0):
    """Reduce overloaded road queries; cache successful subdivisions atomically."""
    west, south, east, north = bounds
    identifier = hashlib.sha256(','.join(f'{v:.8f}' for v in bounds).encode()).hexdigest()[:20]
    path = data_dir()/f'raw/land_price/osm_chunks/bbox-v1-{identifier}.json'
    if cached and path.exists():
        return read_json(path)
    query = (f'[out:json][timeout:90];way[highway][name]'
             f'({south},{west},{north},{east});out geom;')
    try:
        body, endpoint = request(query)
        body['source_endpoint'] = endpoint
        body['queries'] = [query]
    except RuntimeError:
        if depth >= 2:
            raise
        x, y = (west+east)/2, (south+north)/2
        LOGGER.info('Subdividing overloaded OSM road query at depth %s', depth)
        children = [road_chunk(b, cached, depth+1) for b in (
            (west,south,x,y), (x,south,east,y), (west,y,x,north), (x,y,east,north))]
        ways = {w['id']:w for child in children for w in child['elements']}
        endpoints = sorted({u for child in children for u in
                            child.get('source_endpoints', [child.get('source_endpoint', ENDPOINTS[0])])})
        body = {'elements':list(ways.values()), 'source_endpoints':endpoints,
                'source_endpoint':endpoints[0], 'queries':[q for child in children for q in child['queries']],
                'source_times':[child.get('osm3s', {}).get('timestamp_osm_base') for child in children]}
    write_json(path, body)
    return body


def roads(boundary, cached=False):
    cache = data_dir()/'raw/land_price/osm_roads.json'
    if cached and cache.exists():
        result = read_json(cache)
        if result.get('scope') == 'HCMC expanded':
            return result
    from src.pipelines.rainwater.config import Settings
    from src.pipelines.rainwater.grid import build
    city = read_boundary(boundary)
    cells, grid = build(Settings(boundary, grid_m=20000))
    ways, queries, endpoints, source_times = {}, [], set(), []
    for index, cell in enumerate(cells):
        west, south, east, north = shape(cell['geometry']).bounds
        chunk = data_dir()/f'raw/land_price/osm_chunks/{grid["grid_id"]}-{index}.json'
        if cached and chunk.exists():
            body = read_json(chunk)
        else:
            body = road_chunk((west,south,east,north), cached)
            write_json(chunk, body)
        for way in body['elements']:
            coords = [(p['lon'],p['lat']) for p in way.get('geometry',[])]
            if len(coords) >= 2 and LineString(coords).intersects(city):
                ways[way['id']] = way
        queries.extend(body.get('queries', []))
        endpoints.update(body.get('source_endpoints', [body.get('source_endpoint', ENDPOINTS[0])]))
        source_times.extend(body.get('source_times', [body.get('osm3s', {}).get('timestamp_osm_base')]))
        LOGGER.info('OSM roads %s/%s', index+1, len(cells))
    result = {'elements':list(ways.values()), 'queries':queries, 'scope':'HCMC expanded',
        'source_endpoint':sorted(endpoints)[0], 'source_endpoints':sorted(endpoints),
        'source_times':source_times}
    write_json(cache, result)
    return result


def prepare(boundary=None, cached=True):
    boundary = boundary or data_dir()/'inputs/hcmc_expanded_boundary.geojson'
    if not boundary.exists():
        from src.shared.hcmc_boundary import run
        run(cached=True)
    return roads(boundary, cached), wards(boundary, cached)
