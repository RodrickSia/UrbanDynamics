"""Citywide table-based reference prices with permissive automatic placement.

The geometry is sourced OSM geometry. Price values remain published table values;
assignment to a road may use a nearby name or an area reference. This policy is
deliberately different from the strict source-segment matcher.
"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
import re
import unicodedata

from shapely.geometry import LineString, MultiLineString, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from src.shared.data_io import read_json, write_json, utc_now

VERSION = 'automatic-reference-fill-v1'
CATEGORIES = ('residential', 'commercial', 'other_nonagricultural')


def key(value):
    value = unicodedata.normalize('NFKD', str(value).lower().replace('\u0111', 'd'))
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r'\([^)]*\)', ' ', value)
    value = re.sub(r'[^a-z0-9]+', ' ', value).strip()
    value = re.sub(r'^(?:phuong|xa|thi tran|duong|road|street)\s+', '', value)
    return re.sub(r'\s+', ' ', value)


def line_parts(geometry):
    if geometry.geom_type == 'LineString':
        return [geometry] if geometry.length > 0 else []
    if hasattr(geometry, 'geoms'):
        return [line for part in geometry.geoms for line in line_parts(part)]
    return []


def values(row):
    result = {}
    for category in CATEGORIES:
        value = row[category + '_1000_vnd_m2']
        if type(value) is not int or value <= 0:
            raise ValueError('Source prices must be positive integers')
        result[category + '_vnd_m2'] = value * 1000
    return result


def build(source, roads, wards, city, verified):
    rows = source['records']
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows) or source['published_unit'] != '1000 VND/m2':
        raise ValueError('Invalid source IDs or units')
    for row in rows:
        values(row)
    ward_features = wards['features']
    ward_shapes = [shape(f['geometry']) for f in ward_features]
    ward_keys = [key(f['properties']['name']) for f in ward_features]
    ward_index = {k: i for i, k in enumerate(ward_keys)}
    ward_tree = STRtree(ward_shapes)
    resolved_wards = {}
    def resolve_ward(label):
        if label not in resolved_wards:
            normalized = key(label)
            chosen = normalized if normalized in ward_index else get_close_matches(normalized, ward_keys, n=1, cutoff=0)[0]
            resolved_wards[label] = ward_index[chosen]
        return resolved_wards[label]
    ways = []
    local = defaultdict(list)
    local_names = defaultdict(lambda: defaultdict(list))
    global_names = defaultdict(list)
    seen = set()
    for original in roads['elements']:
        if original.get('type') != 'way':
            continue
        if original['id'] in seen:
            raise ValueError('Duplicate road ID')
        seen.add(original['id'])
        coordinates = [(p['lon'], p['lat']) for p in original.get('geometry', [])]
        if len(coordinates) < 2:
            continue
        original_line = LineString(coordinates)
        clipped = original_line if city.covers(original_line) else original_line.intersection(city)
        parts = line_parts(clipped)
        if not parts:
            continue
        geometry = parts[0] if len(parts) == 1 else MultiLineString(parts)
        midpoint = geometry.interpolate(0.5, normalized=True)
        contained = [int(i) for i in ward_tree.query(midpoint, predicate='intersects')]
        wi = min(contained) if contained else int(ward_tree.nearest(midpoint))
        name = original.get('tags', {}).get('name') or original.get('tags', {}).get('name:vi') or f"OSM {original['id']}"
        item = {'id': original['id'], 'name': name, 'key': key(name), 'geometry': geometry, 'ward': wi, 'midpoint': midpoint}
        index = len(ways)
        ways.append(item)
        local[wi].append(index)
        local_names[wi][item['key']].append(index)
        global_names[item['key']].append(index)
    if not ways:
        raise ValueError('No sourced road geometry inside the city')
    # A ward with no road geometry uses the geographically nearest sourced way.
    way_tree = STRtree([w['geometry'] for w in ways])
    row_wards = {r['id']: resolve_ward(r['ward']) for r in rows}
    row_groups = defaultdict(list)
    named_rows = defaultdict(list)
    for row in rows:
        wi = row_wards[row['id']]
        row_groups[wi].append(row)
        named_rows[wi, key(row['road'])].append(row)
    cached_names = {}
    def choose_way(row):
        wi = row_wards[row['id']]
        name = key(row['road'])
        names = local_names[wi]
        if name in names:
            candidates, method, score = names[name], 'same_ward_road_name', 1.0
        elif names:
            cache_key = wi, name
            if cache_key not in cached_names:
                best = get_close_matches(name, list(names), n=1, cutoff=0)[0]
                cached_names[cache_key] = best, SequenceMatcher(None, name, best).ratio()
            best, score = cached_names[cache_key]
            candidates, method = names[best], 'same_ward_similar_name' if score >= .55 else 'same_ward_reference_road'
        else:
            candidates = [int(way_tree.nearest(ward_shapes[wi].representative_point()))]
            method, score = 'nearest_area_reference_road', 0.0
        # Endpoint street proximity ranks actual ways; no invented connecting line.
        anchors = []
        for field in ('from', 'to'):
            ids = names.get(key(row[field]), [])
            if ids:
                anchors.append(ways[ids[0]]['midpoint'])
        if not anchors:
            anchors = [ward_shapes[wi].representative_point()]
        chosen = min(candidates, key=lambda i: (sum(ways[i]['geometry'].distance(a) for a in anchors), ways[i]['id']))
        return chosen, method, score
    existing = {f['id']: f for f in verified.get('features', []) if f['id'] in by_id}
    matches, assignments = [], {}
    methods = Counter()
    for number, row in enumerate(rows, 1):
        identifier = row['id']
        selected, method, score = choose_way(row)
        assignments[identifier] = selected
        if identifier in existing:
            feature = existing[identifier]
            if any(feature['properties'].get(k) != v for k, v in values(row).items()):
                raise ValueError('Previously matched prices differ from source')
            matches.append(feature)
            methods['preserved_existing_segment'] += 1
        else:
            way = ways[selected]
            props = {'id': identifier, 'price_record_id': identifier, 'road': row['road'],
                'start': row['from'], 'end': row['to'], 'ward': row['ward'], 'region_id': row.get('region_id'),
                **values(row), 'unit': 'VND/m2', 'price_kind': 'table_reference',
                'source_url': source['source_url'], 'effective_from': source.get('effective_from'),
                'pdf_page': row.get('pdf_page'), 'geometry_reviewed': False, 'source_values_reviewed': False,
                'publication_match_mode': 'automatic', 'match_method': method,
                'match_confidence': 'automatic_reference', 'matcher_version': VERSION,
                'geometry_coverage': 'actual_road_piece_reference', 'osm_way_ids': [way['id']],
                'matched_road_name': way['name'], 'name_similarity': round(score, 4),
                'ward_osm_relation_id': ward_features[way['ward']]['properties']['osm_relation_id'],
                'geometry_source_url': f"https://www.openstreetmap.org/way/{way['id']}",
                'geometry_license': 'ODbL', 'allocation_note': 'Table price assigned automatically; location and published segment extent may be approximate.'}
            matches.append({'type': 'Feature', 'id': identifier, 'geometry': mapping(way['geometry']), 'properties': props})
            methods[method] += 1
        if number % 1000 == 0:
            print(f'Automatic row placement {number}/{len(rows)}', flush=True)
    verified_by_way = defaultdict(list)
    for feature in existing.values():
        for way_id in feature['properties'].get('osm_way_ids', []):
            verified_by_way[way_id].append(by_id[feature['id']])
    road_features, coverage_methods = [], Counter()
    priced_wards = [wi for wi, group in row_groups.items() if group]
    for number, way in enumerate(ways, 1):
        wi = way['ward']
        candidates = verified_by_way[way['id']] or named_rows[wi, way['key']]
        method = 'existing_segment_reference' if verified_by_way[way['id']] else 'same_ward_road_name'
        if not candidates:
            candidates = row_groups[wi]
            method = 'ward_table_reference'
        if not candidates:
            closest_ward = min(priced_wards, key=lambda j: ward_shapes[j].distance(way['midpoint']))
            candidates, method = row_groups[closest_ward], 'nearest_ward_table_reference'
        # Deterministic central table row: actual PDF triple, not invented values.
        selected = sorted(candidates, key=lambda r: (r['residential_1000_vnd_m2'], r['id']))[len(candidates) // 2]
        props = {'id': f"osm:{way['id']}", 'road': way['name'], 'ward': ward_features[wi]['properties']['name'],
            'region_id': selected.get('region_id'), 'start': selected['from'], 'end': selected['to'],
            **values(selected), 'unit': 'VND/m2', 'price_kind': 'table_reference',
            'effective_from': source.get('effective_from'), 'source_url': source['source_url'],
            'pdf_page': selected.get('pdf_page'), 'price_record_id': selected['id'], 'source_road': selected['road'],
            'osm_way_ids': [way['id']], 'geometry_reviewed': False, 'source_values_reviewed': False,
            'publication_match_mode': 'automatic', 'match_method': method, 'match_confidence': 'automatic_reference',
            'geometry_coverage': 'citywide_road_reference', 'matcher_version': VERSION,
            'geometry_source_url': f"https://www.openstreetmap.org/way/{way['id']}", 'geometry_license': 'ODbL'}
        road_features.append({'type': 'Feature', 'id': f"osm:{way['id']}", 'geometry': mapping(way['geometry']), 'properties': props})
        coverage_methods[method] += 1
        if number % 10000 == 0:
            print(f'Road price coverage {number}/{len(ways)}', flush=True)
    stamp = utc_now()
    meta = {'generated_at': stamp, 'updated_at': stamp, 'source_rows': len(rows), 'matched_rows': len(matches),
        'pending_rows': 0, 'unit': 'VND/m2', 'title': 'Land price references from the published table',
        'policy': VERSION, 'matched_region_counts': dict(Counter(r.get('region_id') for r in rows)),
        'source_pdf_sha256': source.get('source_pdf_sha256'),
        'limitations': 'Automatic table-based reference allocation. Geometry and segment extent may be approximate. Coverage applies to sourced roads inside the analytical city boundary; missing real-world roads are not invented.',
        'row_assignment_methods': dict(methods), 'road_assignment_methods': dict(coverage_methods),
        'road_geometry_count': len(road_features), 'source_url': source['source_url']}
    return ({'type': 'FeatureCollection', 'features': matches, 'metadata': meta},
            {'type': 'FeatureCollection', 'features': road_features, 'metadata': meta})


def run(root, output_dir=None, publish_local=False, publish_warehouse=False):
    root = Path(root)
    out = Path(output_dir) if output_dir else root
    source = read_json(root / 'review/land_price_rows.json')
    verified_path = root / 'review/land_price_verified_segments.geojson'
    current = read_json(root / 'layers/land_price.geojson')
    if verified_path.exists():
        verified = read_json(verified_path)
    elif current.get('metadata', {}).get('policy') == VERSION:
        raise ValueError('Original verified segment snapshot is required')
    else:
        verified = current
    city = unary_union([shape(f['geometry']) for f in read_json(root / 'inputs/hcmc_expanded_boundary.geojson')['features']])
    matches, coverage = build(source, read_json(root / 'raw/land_price/osm_roads.json'),
        read_json(root / 'inputs/land_price_wards.geojson'), city, verified)
    goal_file = root / 'review/land_price_pending.baseline_7080.json'
    goal = {r['id'] for r in read_json(goal_file)['pending']} if goal_file.exists() else set()
    matched = {f['id'] for f in matches['features']}
    if goal - matched or len(matched) != len(source['records']):
        raise ValueError('Automatic fill did not account for the entire source/goal scope')
    report = {'source_rows': len(matched), 'goal_rows': len(goal), 'goal_mapped': len(goal & matched),
        'goal_pending': len(goal - matched), 'preserved_verified_rows': len(verified['features']),
        'road_features_with_price': len(coverage['features']), 'policy': VERSION,
        'row_assignment_methods': matches['metadata']['row_assignment_methods'], 'approximate_placement_authorized': True}
    write_json(out / 'review/land_price_verified_segments.geojson', verified)
    write_json(out / 'review/land_price_row_matches.geojson', matches)
    write_json(out / 'layers/land_price.geojson', coverage)
    write_json(out / 'review/land_price_pending.json', {'pending': [], 'matched': sorted(matched)})
    write_json(out / 'review/land_price_automatic_fill_report.json', report)
    catalogue = []
    feature_by_id = {f['id']: f for f in matches['features']}
    for row in source['records']:
        catalogue.append({**row, **values(row), 'has_geometry': True, 'map_status': 'mapped_automatic',
            'geometry': feature_by_id[row['id']]['geometry'], 'pending_reason': None})
    write_json(out / 'review/land_price_catalog.json', {'records': catalogue, 'metadata': matches['metadata']})
    if publish_local and out.resolve() != root.resolve():
        for relative in ('review/land_price_verified_segments.geojson', 'review/land_price_row_matches.geojson',
                         'layers/land_price.geojson', 'review/land_price_pending.json',
                         'review/land_price_automatic_fill_report.json', 'review/land_price_catalog.json'):
            write_json(root / relative, read_json(out / relative))
    if publish_warehouse:
        from src.shared.database import publish
        publish('land_price', coverage, root=root)
    return report
