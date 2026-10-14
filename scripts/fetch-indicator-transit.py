"""Publish a bounded OSM stop snapshot. Run explicitly; API requests stay offline."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('etl/data/transit/stops.geojson'))
    parser.add_argument('--endpoint', choices=['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter'], default='https://overpass-api.de/api/interpreter')
    args = parser.parse_args()
    west, south, east, north = 106.2, 10.3, 107.2, 11.3
    bbox = f'{south},{west},{north},{east}'
    query = f'[out:json][timeout:60];(nwr[highway=bus_stop]({bbox});nwr[railway~"^(station|halt|tram_stop)$"]({bbox}););out center;'
    response = requests.get(args.endpoint, params={'data': query}, timeout=90,
                             headers={'User-Agent': 'UrbanDynamics/1.0 (public transit snapshot)'})
    response.raise_for_status()
    payload = response.json()
    if payload.get('remark'):
        raise ValueError('Overpass returned an incomplete query; snapshot not published')
    features = []
    for item in payload['elements']:
        point = item if 'lat' in item else item.get('center', {})
        if 'lat' not in point:
            continue
        tags = item.get('tags', {})
        features.append({'type': 'Feature', 'id': f"{item['type']}/{item['id']}",
                         'geometry': {'type': 'Point', 'coordinates': [point['lon'], point['lat']]},
                         'properties': {'name': tags.get('name', 'Transit stop'),
                                        'mode': 'bus' if tags.get('highway') == 'bus_stop' else 'rail'}})
    document = {'type': 'FeatureCollection', 'bbox': [west, south, east, north],
                'source': 'OpenStreetMap contributors · ODbL · https://www.openstreetmap.org/copyright',
                'captured_at': datetime.now(timezone.utc).isoformat(),
                'source_timestamp': payload.get('osm3s', {}).get('timestamp_osm_base'),
                'features': features}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    temporary.replace(args.output)
    print(f'Published {len(features)} stops to {args.output}')


if __name__ == '__main__':
    main()
