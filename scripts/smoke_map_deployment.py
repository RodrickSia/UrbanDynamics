"""Read-only smoke checks through the deployed frontend's same-origin proxy."""
import argparse
import json
import math
from time import perf_counter
from urllib.error import HTTPError
from urllib.request import urlopen


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_deployment(fetch):
    def document(path):
        status, content_type, body = fetch(path)
        require(status == 200 and 'application/json' in content_type,
                f'{path}: expected JSON HTTP 200, got {status} {content_type}')
        return json.loads(body)

    status, content_type, body = fetch('/')
    require(status == 200 and 'text/html' in content_type and b'/assets/' in body,
            'Frontend build is not served at /')
    require(document('/health').get('status') == 'ok', 'Backend health failed')
    require(document('/ready').get('status') == 'ready', 'Backend storage is not ready')
    paths = document('/api/v1/openapi.json')['paths']
    require('/api/v1/layers' in paths and '/api/v1/population' in paths,
            'Backend map routes missing')
    population = document('/api/v1/population')
    require(population.get('available') and population.get('years'), 'No population data loaded')
    years = sorted(item['year'] for item in population['years'])
    year = years[-1]
    sample = document(f'/api/v1/population/{year}/value?lng=106.7&lat=10.8')
    require(not sample.get('nodata') and isinstance(sample.get('population'), (int, float)),
            'Population sample unavailable in HCMC')
    x = math.floor((106.7 + 180) / 360 * 2**10)
    y = math.floor((1 - math.asinh(math.tan(math.radians(10.8))) / math.pi) / 2 * 2**10)
    status, content_type, body = fetch(f'/api/v1/population/{year}/tiles/10/{x}/{y}.png?render=2')
    require(status == 200 and 'image/png' in content_type and body.startswith(b'\x89PNG\r\n\x1a\n'),
            'Population PNG tile failed through frontend proxy')

    results, unavailable = {}, []
    supported = {'flood_history', 'flood_satellite', 'flood_risk', 'land_price', 'parcels'}
    for layer in document('/api/v1/layers')['layers']:
        name = layer['id']
        if name not in supported:
            continue
        if not layer.get('available'):
            unavailable.append(name)
            continue
        root = f'/api/v1/layers/{name}'
        features = document(root + '/features?limit=1')
        require(features.get('type') == 'FeatureCollection' and isinstance(features.get('features'), list),
                f'{name}: invalid GeoJSON response')
        tilejson = document(root + '/tilejson.json')
        require(tilejson.get('tiles'), f'{name}: missing tile template')
        # Request our same origin, not the internal hostname a proxy may advertise.
        status, content_type, body = fetch(root + f'/tiles/10/{x}/{y}.pbf')
        require(status == 204 or (status == 200 and body and 'application/vnd.mapbox-vector-tile' in content_type),
                f'{name}: vector tile failed with HTTP {status} {content_type}')
        results[name] = {'sample_features': len(features['features']), 'tile_status': status}
        if name == 'land_price':
            results[name]['matched_rows'] = tilejson.get('metadata', {}).get('matched_rows')
        if name == 'parcels' and features['features']:
            feature = features['features'][0]
            detail = document(f"/api/v1/parcels/{feature['id']}")
            require(detail.get('land_use', {}).get('color') and detail.get('price', {}).get('status'),
                    'Parcel details missing color or price status')
            point = feature['geometry']['coordinates']
            while isinstance(point[0], list):
                point = point[0]
            longitude, latitude = point[:2]
            levels = {}
            for zoom in (12, 14, 16):
                tx = math.floor((longitude + 180) / 360 * 2**zoom)
                ty = math.floor((1 - math.asinh(math.tan(math.radians(latitude))) / math.pi) / 2 * 2**zoom)
                started = perf_counter()
                status, mime, tile = fetch(root + f'/tiles/{zoom}/{tx}/{ty}.pbf?schema=2')
                require(status == 204 or (status == 200 and tile and 'application/vnd.mapbox-vector-tile' in mime),
                        f'Parcel zoom {zoom} tile failed')
                if zoom == 16:
                    require(status == 200, 'Known parcel is absent from its native tile')
                levels[zoom] = {'status': status, 'bytes': len(tile), 'elapsed_ms': round((perf_counter()-started)*1000)}
            results[name].update(detail_status='ok', tile_levels=levels)
    return {'status': 'ok', 'population_years': years, 'vector_layers': results,
            'unavailable_layers': unavailable}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', help='Frontend origin, e.g. http://127.0.0.1:51873')
    args = parser.parse_args()

    def fetch(path):
        try:
            with urlopen(args.base_url.rstrip('/') + path, timeout=60) as response:
                return response.status, response.headers.get('Content-Type', ''), response.read()
        except HTTPError as error:
            return error.code, error.headers.get('Content-Type', ''), b''

    print(json.dumps(check_deployment(fetch), indent=2))


if __name__ == '__main__':
    main()
