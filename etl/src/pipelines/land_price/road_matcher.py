"""Conservative spatial matching: current ward, exact road name, unique path.

No fuzzy matches, guessed coordinates, gap bridging or shortest-path guesses.
Unresolved and ambiguous rows carry explicit review reasons.
"""
from collections import Counter, deque
import re

from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import linemerge, substring, transform, unary_union

from src.pipelines.flood_history.transform import normalize
from .road_sources import ward_name

VERSION = 'ward-unique-path-v1'
METHODS = {'spatial_ward_unique_path', 'spatial_ward_whole_road'}
PROJECT = Transformer.from_crs(4326, 32648, always_xy=True).transform
UNPROJECT = Transformer.from_crs(32648, 4326, always_xy=True).transform


def road_keys(value):
    # Parenthetical names/refs are explicit aliases, not fuzzy similarity.
    value = re.sub(r',\s*(?:PHƯỜNG|XÃ|ĐẶC KHU)\b.*$', '', value, flags=re.I)
    aliases = [re.sub(r'\([^)]*\)', '', value)] + re.findall(r'\(([^)]*)\)', value)
    result = set()
    for alias in aliases:
        key = normalize(re.sub(r'^\s*(?:ĐƯỜNG|GIAO\s+(?:VỚI|ĐƯỜNG))\s+', '', alias, flags=re.I))
        if key:
            result.add(key)
            if re.fullmatch(r'(quoclo|ql)\d+[a-z]?', key):
                result.add(re.sub(r'^(quoclo|ql)', 'ql', key))
    return result


def lines(geometry):
    if geometry.geom_type == 'LineString':
        return [geometry] if geometry.length > .01 else []
    if geometry.geom_type in ('MultiLineString', 'GeometryCollection'):
        return [line for part in geometry.geoms for line in lines(part)]
    return []


def points(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Point':
        return [geometry]
    if geometry.geom_type in ('MultiPoint', 'GeometryCollection'):
        result = []
        for part in geometry.geoms:
            result.extend(points(part))
        return result
    # Collinear road names / overlap do not identify one intersection.
    raise ValueError('endpoint_overlap')


def key(point):
    return round(point.x, 2), round(point.y, 2)


class RoadGraph(dict):
    def __init__(self):
        super().__init__()
        self.parallel_edges = set()


def graph_for(geometry, endpoints):
    graph = RoadGraph()
    for line in lines(unary_union(lines(geometry))):
        locations = {0.0, line.length}
        locations.update(line.project(p) for p in endpoints if line.distance(p) < .02)
        locations = sorted(locations)
        for a, b in zip(locations, locations[1:]):
            part = substring(line, a, b)
            if part.geom_type != 'LineString' or part.length < .02:
                continue
            s, t = key(Point(part.coords[0])), key(Point(part.coords[-1]))
            previous = graph.get(s, {}).get(t)
            if previous is not None and previous.hausdorff_distance(part) > .02:
                graph.parallel_edges.add(frozenset((s,t)))
            # A closed loop is ambiguous unless a later split separates it.
            graph.setdefault(s, {})[t] = part
            graph.setdefault(t, {})[s] = LineString(list(part.coords)[::-1])
    return graph


def components(graph):
    remaining, result = set(graph), []
    while remaining:
        component, queue = set(), [next(iter(remaining))]
        while queue:
            node = queue.pop()
            if node in component:
                continue
            component.add(node)
            queue.extend(set(graph[node]) - component)
        remaining -= component
        result.append(component)
    return result


def connected(graph, start, end, omitted=None):
    queue, parents = deque([start]), {start: None}
    while queue:
        node = queue.popleft()
        if node == end:
            path = []
            while parents[node] is not None:
                previous = parents[node]
                path.append((previous, node))
                node = previous
            return path[::-1]
        for other in graph[node]:
            if frozenset((node, other)) == omitted or other in parents:
                continue
            parents[other] = node
            queue.append(other)
    return None


def road_level(tags):
    if 'layer' in tags:
        return str(tags['layer'])
    if tags.get('bridge') not in (None, 'no'):
        return '1'
    if tags.get('tunnel') not in (None, 'no'):
        return '-1'
    return '0'


def endpoint_geometry(text, named_roads, ward, target_ways, way_tags):
    matches = {item[0]:item for name in road_keys(text) for item in named_roads.get(name, [])}
    if not matches:
        raise ValueError('endpoint_road_missing')
    # Allow the crossing road at the ward boundary, not elsewhere in the city.
    intersections = []
    for identifier, geometry in matches.values():
        for target_id, target in target_ways:
            # A flyover crossing is not a named at-grade intersection.
            if road_level(way_tags[identifier]) != road_level(way_tags[target_id]):
                continue
            intersections.append(geometry.intersection(ward.buffer(2)).intersection(target))
    return unary_union(intersections)


def clip_unique_path(road, start_road, end_road, allow_dual=False):
    # Computed intersection points must not be intersected a second time:
    # floating point projection can move them microscopically off the line.
    starts = points(start_road if start_road.geom_type in ('Point','MultiPoint') else road.intersection(start_road))
    ends = points(end_road if end_road.geom_type in ('Point','MultiPoint') else road.intersection(end_road))
    if not starts or not ends:
        raise ValueError('endpoint_not_intersecting')
    graph = graph_for(road, starts + ends)
    paths = []
    for component in components(graph):
        s = {key(p) for p in starts} & component
        t = {key(p) for p in ends} & component
        if not s or not t:
            continue
        if len(s) != 1 or len(t) != 1:
            raise ValueError('multiple_endpoint_intersections')
        first, last = next(iter(s)), next(iter(t))
        if first == last:
            raise ValueError('identical_endpoints')
        path = connected(graph, first, last)
        if not path:
            continue
        # Every selected edge must be a bridge: otherwise another route exists.
        if any(frozenset(edge) in graph.parallel_edges or
               connected(graph, first, last, frozenset(edge)) is not None for edge in path):
            raise ValueError('ambiguous_road_path')
        parts = [graph[a][b] for a, b in path]
        paths.append(linemerge(parts) if len(parts) > 1 else parts[0])
    if not paths:
        raise ValueError('disconnected_endpoints')
    if any(g.length < 10 for g in paths):
        raise ValueError('segment_too_short')
    # Two carriageways can share an official road segment. Separate similarly
    # named streets within one ward must not be joined into one price feature.
    if len(paths) > 2 or (len(paths) == 2 and (not allow_dual or paths[0].hausdorff_distance(paths[1]) > 50)):
        raise ValueError('multiple_road_corridors')
    return unary_union(paths), len(starts), len(ends)


def whole_road(road, allow_dual=False):
    parts = lines(road)
    graph = graph_for(road, [])
    groups = components(graph)
    if len(groups) > 1:
        groups_geometry = []
        for group in groups:
            group_parts = [g for node in group for other,g in graph[node].items() if node < other]
            groups_geometry.append(unary_union(group_parts))
        if not allow_dual or len(groups_geometry) != 2 or groups_geometry[0].hausdorff_distance(groups_geometry[1]) > 50:
            raise ValueError('disconnected_named_road')
    if not parts or road.length < 10:
        raise ValueError('segment_too_short')
    return road


def match(source, road_document, ward_document):
    named_roads, ward_index = {}, {}
    way_tags = {way['id']:way.get('tags',{}) for way in road_document['elements']}
    for way in road_document['elements']:
        coords = [(p['lon'],p['lat']) for p in way.get('geometry', [])]
        if len(coords) < 2:
            continue
        geometry = transform(PROJECT, LineString(coords))
        for name in road_keys(way.get('tags', {}).get('name', '')) | road_keys(way.get('tags', {}).get('ref', '')):
            named_roads.setdefault(name, []).append((way['id'], geometry))
    for feature in ward_document['features']:
        prop = feature['properties']
        if prop.get('admin_level') != '6':
            continue
        ward_index.setdefault(prop.get('ward_key') or ward_name(prop['name']), []).append(feature)
    # Current commune names must be unique across the three PDF region groups.
    ward_regions = {}
    for row in source['records']:
        ward_regions.setdefault(ward_name(row.get('ward', '')), set()).add(row.get('region_id'))
    outputs, pending, cache = [], [], {}
    for row in source['records']:
        reason = None
        try:
            if row.get('duplicate_identity_review_required'):
                raise ValueError('duplicate_source_identity')
            wk = ward_name(row.get('ward', ''))
            candidates = ward_index.get(wk, [])
            if not candidates:
                raise ValueError('current_ward_boundary_missing')
            if len(candidates) != 1 or len(ward_regions[wk]) != 1:
                raise ValueError('ambiguous_ward_identity')
            ward_feature = candidates[0]
            ward = transform(PROJECT, shape(ward_feature['geometry']))
            names = tuple(sorted(road_keys(row['road'])))
            ck = (wk, names)
            if ck not in cache:
                ways = {item[0]:item for name in names for item in named_roads.get(name, [])
                        if item[1].intersects(ward)}
                road = unary_union([g.intersection(ward) for _,g in ways.values()])
                cache[ck] = (road, list(ways))
            road, way_ids = cache[ck]
            if not lines(road):
                raise ValueError('named_road_missing_in_ward')
            full = row.get('segment_scope') == 'whole_road' or (
                normalize(row['from']) == 'tronduong' and normalize(row['to']) == 'tronduong')
            allow_dual = all(way_tags[i].get('oneway') in ('yes','1','-1') and
                way_tags[i].get('highway') in ('motorway','trunk','primary','secondary','tertiary') for i in way_ids)
            if full:
                selected = whole_road(road,allow_dual)
                method, coverage = 'spatial_ward_whole_road', 'whole_road_within_ward'
                evidence = {}
            else:
                targets = {item[0]:item for name in names for item in named_roads.get(name, [])
                           if item[0] in way_ids}
                a = endpoint_geometry(row['from'], named_roads, ward, targets.values(), way_tags)
                b = endpoint_geometry(row['to'], named_roads, ward, targets.values(), way_tags)
                selected, starts, ends = clip_unique_path(road, a, b,allow_dual)
                method, coverage = 'spatial_ward_unique_path', 'between_named_intersections_within_ward'
                evidence = {'start_intersections': starts, 'end_intersections': ends}
            properties = {'price_record_id':row['id'], 'road':row['road'], 'ward':row.get('ward'),
                'region_id':row.get('region_id'), 'auto_approved':True, 'reviewed':False,
                'price_values_reviewed':False, 'match_method':method, 'matcher_version':VERSION,
                'match_confidence':'spatially_checked', 'geometry_coverage':coverage,
                'osm_way_ids':way_ids, 'ward_osm_relation_id':ward_feature['properties'].get('osm_relation_id'),
                'geometry_source_url':road_document.get('source_endpoint'), 'geometry_license':'ODbL 1.0',
                'ward_source_url':ward_feature['properties'].get('source_url'),
                'endpoint_evidence':evidence, 'matched_length_m':round(selected.length,2),
                'review_note':'Automatic OSM spatial checks; current commune and unique named-road path. PDF extraction and legal segment limits still require verification.'}
            outputs.append({'type':'Feature','id':row['id'], 'geometry':mapping(transform(UNPROJECT,selected)),
                'properties':properties})
        except ValueError as error:
            reason = str(error)
        if reason:
            pending.append({**row, 'unmatched_reason':reason})
    metadata = {'matcher_version':VERSION, 'source_rows':len(source['records']),
        'matched_rows':len(outputs), 'pending_rows':len(pending),
        'matched_region_counts':dict(Counter(f['properties']['region_id'] for f in outputs)),
        'pending_reason_counts':dict(Counter(r['unmatched_reason'] for r in pending)),
        'ward_boundary_count':len(ward_document['features']), 'scope':'HCMC expanded',
        'limitations':'Automatic spatial matches using OSM analytical boundaries. Not cadastral validation; unreviewed PDF candidates remain explicitly labelled.'}
    return {'type':'FeatureCollection','features':outputs,'metadata':metadata}, pending
