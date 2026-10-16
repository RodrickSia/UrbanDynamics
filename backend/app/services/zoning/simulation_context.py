"""Bounded, immutable local context. Topology is sourced; OD remains a scenario."""
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

from ..simulation.engine import polygon_and_area
from ..simulation.integrated.background import osm_features
from ..simulation.integrated.context import projection
from ..simulation.models import PolygonInput


def warehouse_network(bounds):
    """Read the team's indexed OSM-derived graph instead of downloading a city."""
    from src.shared.database import warehouse_configured, connect_to_warehouse
    from psycopg import Error as DatabaseError
    if not warehouse_configured():
        return None
    try:
        with connect_to_warehouse() as connection:
            connection.execute("SET LOCAL statement_timeout = '8s'")
            if connection.execute("SELECT to_regclass('transport.sumo_edge')").fetchone()[0] is None:
                return None
            rows=connection.execute('''SELECT e.edge_id,e.from_node,e.to_node,e.road_type,e.lanes,
                ST_AsGeoJSON(e.geom),ST_X(f.geom),ST_Y(f.geom),f.junction_type,
                ST_X(t.geom),ST_Y(t.geom),t.junction_type,e.loaded_at
                FROM transport.sumo_edge e
                LEFT JOIN transport.sumo_junction f ON f.junction_id=e.from_node
                LEFT JOIN transport.sumo_junction t ON t.junction_id=e.to_node
                WHERE e.geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)
                ORDER BY e.edge_id LIMIT 5001''',bounds).fetchall()
    except (OSError,DatabaseError):
        return None
    if not rows or len(rows)>5000:
        return None
    nodes, ways, source_edges = {}, [], {}
    def node_id(identifier):
        return int(hashlib.sha256(identifier.encode()).hexdigest()[:15],16)
    for edge, start, end, road_type, lanes, geometry, fx, fy, ft, tx, ty, tt, loaded in rows:
        def usable(lane):
            allow=set((lane.get('allow') or '').split())
            disallow=set((lane.get('disallow') or '').split())
            return (not allow or 'all' in allow or {'passenger','motorcycle'} <= allow) and not ({'all','passenger','motorcycle'} & disallow)
        allowed=[lane for lane in lanes if usable(lane)]
        if not allowed:
            continue
        coordinates=json.loads(geometry)['coordinates']
        start_id,end_id=node_id(start),node_id(end)
        for identifier,x,y,kind,fallback in [(start_id,fx,fy,ft,coordinates[0]),(end_id,tx,ty,tt,coordinates[-1])]:
            nodes.setdefault(identifier,{'type':'node','id':identifier,'lon':x if x is not None else fallback[0],
                'lat':y if y is not None else fallback[1], 'tags':{'highway':'traffic_signals'} if kind and kind.startswith('traffic_light') else {}})
        ids=[start_id]
        for index,point in enumerate(coordinates[1:-1]):
            identifier=node_id(edge+':shape:'+str(index))
            nodes[identifier]={'type':'node','id':identifier,'lon':point[0],'lat':point[1]}
            ids.append(identifier)
        ids.append(end_id)
        identifier=len(ways)+1
        source_edges[str(identifier)]=edge
        speeds=[lane['speed_mps'] for lane in allowed if lane.get('speed_mps') is not None]
        ways.append({'type':'way','id':identifier,'nodes':ids,
            'geometry':[{'lon':nodes[i]['lon'],'lat':nodes[i]['lat']} for i in ids],
            'tags':{'highway':(road_type or 'highway.residential').split('.')[-1], 'oneway':'yes',
                    'lanes':str(len(allowed)),'maxspeed':str(max(speeds)*3.6 if speeds else 30),
                    'urbandynamics:source_edge':edge}})
    if len(ways)<4 or len(nodes)>20000:
        return None
    return {'bbox':bounds,'osm':{'elements':list(nodes.values())+ways},
            'captured_at':datetime.now(timezone.utc).isoformat(),
            'source':'Team warehouse transport.sumo_edge: local reconstruction of the stored OSM-derived directed graph. Turn restrictions and original phase timings are not preserved.',
            'network_kind':'warehouse_osm_reconstruction','source_edges':source_edges,
            'warehouse_loaded_at_range':[str(min(r[-1] for r in rows)),str(max(r[-1] for r in rows))]}


def directory():
    return Path(os.getenv('DEVELOPMENT_CONTEXT_DIR', 'data/development_context'))


def _load(path, identifier):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != identifier:
        raise ValueError('Local OSM context integrity check failed')
    return json.loads(raw)


def load_network(identifier):
    if len(identifier) != 64 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('Invalid local OSM context identifier')
    return _load(directory() / (identifier + '.json'), identifier)


def available_document(region):
    """Reuse installed historical surfaces only when they contain the full scope."""
    root = Path(os.getenv('PLANNING_SYSTEM_SNAPSHOT_DIR', 'data/simulation_snapshots'))
    candidates = []
    for path in sorted(root.glob('*.json'))[:40]:
        try:
            document = _load(path, path.stem)
            if box(*document['bbox']).covers(region):
                document['_installed_snapshot_id'] = path.stem
                candidates.append(document)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return next((d for d in candidates if d.get('landcover')), candidates[0] if candidates else None)


def acquire_network(region, radius_m):
    """Prepare roads around ANY supported geographic scope; never fake topology."""
    west, south, east, north = region.bounds
    latitude = (south + north) / 2
    if abs(latitude) > 80:
        raise ValueError('Local traffic preparation supports latitudes within ±80 degrees')
    dy = radius_m / 110540
    dx = radius_m / (111320 * math.cos(math.radians(latitude)))
    bounds = [round(west-dx, 5), round(south-dy, 5), round(east+dx, 5), round(north+dy, 5)]
    if (bounds[2]-bounds[0])*111320*math.cos(math.radians(latitude))*(bounds[3]-bounds[1])*110540 > 25_000_000:
        raise ValueError('Traffic area exceeds 25 km²; choose a smaller study area or road radius')
    key = hashlib.sha256(json.dumps(bounds).encode()).hexdigest()
    root = directory()
    pointer = root / ('area-' + key + '.json')
    if pointer.is_file():
        try:
            identifier = json.loads(pointer.read_text())['snapshot_id']
            return identifier, load_network(identifier)
        except (OSError, ValueError, KeyError):
            pass
    warehouse = warehouse_network(bounds)
    installed = None if warehouse else available_document(box(*bounds))
    if warehouse:
        document = warehouse
    elif installed:
        document = {k: installed[k] for k in ('osm', 'captured_at') if k in installed}
        document.update(bbox=bounds, source='Installed OSM extract; clipped to the requested local road boundary')
    else:
        query = '[out:json][timeout:12];way[highway]({s},{w},{n},{e});out geom;'.format(w=bounds[0],s=bounds[1],e=bounds[2],n=bounds[3])
        errors = []
        for endpoint in ('https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter'):
            try:
                request = Request(endpoint, data=urlencode({'data': query}).encode(),
                                  headers={'User-Agent': 'UrbanDynamics/2026 (urban-planning research; https://github.com/RodrickSia/UrbanDynamics)',
                                           'Accept':'application/json'})
                with urlopen(request, timeout=16) as response:
                    raw = response.read(15_000_001)
                if len(raw) > 15_000_000:
                    raise ValueError('OSM response exceeds local study limit')
                osm = json.loads(raw)
                if osm.get('remark') or not osm.get('elements'):
                    raise ValueError('OSM returned no complete local extract')
                document = {'bbox':bounds, 'osm':osm, 'source':endpoint,
                            'captured_at':datetime.now(timezone.utc).isoformat()}
                break
            except (URLError, OSError, ValueError, TimeoutError) as error:
                errors.append(type(error).__name__ + (str(getattr(error,'code',''))))
        else:
            raise ValueError('Local OSM roads could not be downloaded. Retry later or install a local extract. '
                             'No synthetic road fallback was used. (' + ', '.join(errors) + ')')
    document.update(schema_version=1, bbox=bounds, radius_m=radius_m,
                    attribution='© OpenStreetMap contributors, ODbL',
                    limitations='Road topology only. Access connectors, signal timings and OD are not surveyed.')
    ways = [e for e in document['osm'].get('elements', []) if e.get('type') == 'way' and e.get('tags', {}).get('highway')]
    if not ways:
        raise ValueError('No OSM roads found around this study area')
    raw = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
    identifier = hashlib.sha256(raw).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    immutable_temp = root / (identifier + '-' + uuid4().hex + '.tmp')
    immutable_temp.write_bytes(raw)
    immutable_temp.replace(root / (identifier + '.json'))
    # Atomic pointer publication; content-addressed documents are immutable.
    temporary = root / ('area-' + key + '-' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps({'snapshot_id':identifier}))
    temporary.replace(pointer)
    return identifier, document


def surfaces(site, buildings, document=None):
    """Remove current roofs before classifying ground; unknown ground stays labelled."""
    geometry = shape(site.model_dump() if hasattr(site, 'model_dump') else site)
    area = polygon_and_area(PolygonInput(**geometry.__geo_interface__))[1]
    forward, _ = projection(geometry)
    metric_site = transform(forward, geometry)
    roofs = unary_union([transform(forward, shape(b['footprint'])) for b in buildings])
    roof_area = sum(polygon_and_area(PolygonInput(**b['footprint']))[1] for b in buildings)
    remaining = max(0, area-roof_area)
    greens, paved = [], []
    if document:
        _, osm_greens, _ = osm_features(document.get('osm', {}))
        greens += [transform(forward, shape(f['geometry'])) for f in osm_greens]
        for feature in document.get('landcover', {}).get('features', []):
            code = feature['properties']['class_code']
            if code in (10,20,30,40,90,95,100):
                greens.append(transform(forward, shape(feature['geometry'])))
            elif code == 50:
                paved.append(transform(forward, shape(feature['geometry'])))
    green_geometry = unary_union(greens).intersection(metric_site).difference(roofs)
    scale = area/metric_site.area
    known_green = min(remaining, green_geometry.area*scale)
    known_paved = min(remaining-known_green, unary_union(paved).intersection(metric_site).difference(roofs).difference(green_geometry).area*scale)
    unknown = max(0, remaining-known_green-known_paved)
    return {'buildings':buildings, 'green_m2':known_green + unknown*.4,
            'paved_m2':known_paved + unknown*.5, 'permeable_m2':unknown*.1}, {
                'status':'mixed_source_and_assumptions' if document else 'assumed',
                'mapped_green_m2':known_green, 'built_up_paved_proxy_m2':known_paved,
                'unclassified_surface_m2':unknown, 'unknown_split':{'green':.4,'paved':.5,'permeable':.1},
                'landcover':document.get('landcover', {}).get('metadata') if document else None,
                'snapshot_id':document.get('_installed_snapshot_id') if document else None,
                'note':'OSM green areas and historical WorldCover where available; unclassified ground uses an explicit 40% green / 50% paved / 10% permeable assumption. Built-up pixels are a paving proxy, not a survey.'}


def traffic_prior():
    from ..simulation.planning import counting_reference
    from ..simulation.planning.models import TrafficPrior
    identifier = counting_reference.default_identifier()
    if identifier:
        try:
            return counting_reference.prior(identifier)
        except (OSError, ValueError):
            # The optional demo reference may be installed while demo mode is
            # disabled. It must not prevent an ordinary plan simulation.
            pass
    return TrafficPrior(cars=[100]*24, motorcycles=[300]*24, source_kind='synthetic',
                        source='Fallback scenario: 400 vehicles/hour (100 cars + 300 motorcycles), constant daily profile. Not observed traffic at the selected site; no calibrated OD.')
