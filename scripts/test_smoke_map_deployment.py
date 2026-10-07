import json
import unittest

from smoke_map_deployment import check_deployment


class DeploymentSmokeTests(unittest.TestCase):
    def setUp(self):
        self.overrides = {}

    def fetch(self, path):
        if path in self.overrides:
            return self.overrides[path]
        if path == '/':
            return 200, 'text/html', b'<script src="/assets/app.js"></script>'
        if path.endswith('.png?render=2'):
            return 200, 'image/png', b'\x89PNG\r\n\x1a\n' + b'fixture'
        if path.endswith('.pbf'):
            return 204, '', b''
        body = {
            '/health': {'status': 'ok'},
            '/ready': {'status': 'ready'},
            '/api/v1/openapi.json': {'paths': {'/api/v1/layers': {}, '/api/v1/population': {}}},
            '/api/v1/population': {'available': True, 'years': [{'year': 2024}]},
            '/api/v1/population/2024/value?lng=106.7&lat=10.8': {'population': 42, 'nodata': False},
            '/api/v1/layers': {'layers': [
                {'id': 'land_price', 'available': True},
                {'id': 'flood_risk', 'available': False},
            ]},
            '/api/v1/layers/land_price/features?limit=1': {'type': 'FeatureCollection', 'features': []},
            '/api/v1/layers/land_price/tilejson.json': {'tiles': ['/tiles'], 'metadata': {'matched_rows': 42}},
        }[path]
        return 200, 'application/json', json.dumps(body).encode()

    def test_reports_published_and_unavailable_layers_and_accepts_empty_tile(self):
        result = check_deployment(self.fetch)
        self.assertEqual(result['vector_layers']['land_price']['tile_status'], 204)
        self.assertEqual(result['unavailable_layers'], ['flood_risk'])
        self.assertEqual(result['population_years'], [2024])

    def test_rejects_spa_fallback_instead_of_backend_json(self):
        self.overrides['/health'] = 200, 'text/html', b'<html>SPA</html>'
        with self.assertRaisesRegex(RuntimeError, '/health'):
            check_deployment(self.fetch)

    def test_rejects_broken_tile_even_when_health_is_green(self):
        self.overrides['/api/v1/layers/land_price/tiles/10/815/481.pbf'] = 503, 'application/json', b'{}'
        with self.assertRaisesRegex(RuntimeError, 'land_price'):
            check_deployment(self.fetch)

    def test_rejects_missing_population_data(self):
        self.overrides['/api/v1/population'] = 200, 'application/json', b'{"available":false,"years":[]}'
        with self.assertRaisesRegex(RuntimeError, 'population'):
            check_deployment(self.fetch)

    def test_parcels_probe_real_native_zoom_and_details(self):
        def parcel_fetch(path):
            documents = {
                '/api/v1/layers': {'layers': [{'id': 'parcels', 'available': True}]},
                '/api/v1/layers/parcels/features?limit=1': {'type': 'FeatureCollection', 'features': [
                    {'id': 42, 'geometry': {'coordinates': [[[[106.7,10.8]]]]}}]},
                '/api/v1/layers/parcels/tilejson.json': {'tiles': ['/tiles']},
                '/api/v1/parcels/42': {'land_use': {'color': '#d6604d'}, 'price': {'status': 'unavailable'}},
            }
            if path in documents:
                return 200, 'application/json', json.dumps(documents[path]).encode()
            if path.endswith('?schema=2'):
                return 200, 'application/vnd.mapbox-vector-tile', b'tile-fixture'
            return self.fetch(path)
        result = check_deployment(parcel_fetch)['vector_layers']['parcels']
        self.assertEqual(result['detail_status'], 'ok')
        self.assertEqual(result['tile_levels'][16]['status'], 200)


if __name__ == '__main__':
    unittest.main()
