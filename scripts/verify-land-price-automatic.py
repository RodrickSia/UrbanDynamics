"""Verify the full permissive allocation against cached source roads and prices."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'etl'), str(ROOT / 'backend')]
from shapely.geometry import LineString, shape
from shapely.ops import unary_union
from shapely.prepared import prep
from src.shared.data_io import read_json, write_json
from src.shared.database import _validate_document
from src.pipelines.land_price.automatic_fill import CATEGORIES, line_parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'etl/data')
    parser.add_argument('--snapshot-dir', type=Path)
    parser.add_argument('--api', action='store_true')
    args = parser.parse_args()
    root, snapshot = args.data_dir, args.snapshot_dir or args.data_dir
    source = read_json(root / 'review/land_price_rows.json')
    rows = {r['id']: r for r in source['records']}
    matches = read_json(snapshot / 'review/land_price_row_matches.geojson')
    coverage = read_json(snapshot / 'layers/land_price.geojson')
    verified = read_json(snapshot / 'review/land_price_verified_segments.geojson')
    mapped = {f['id']: f for f in matches['features']}
    goal = {r['id'] for r in read_json(root / 'review/land_price_pending.baseline_7080.json')['pending']}
    assert len(rows) == len(source['records']) == len(matches['features']) == len(mapped)
    assert rows.keys() == mapped.keys() and goal <= mapped.keys() and len(goal) == 7080
    assert read_json(snapshot / 'review/land_price_pending.json')['pending'] == []
    assert all(mapped[f['id']] == f for f in verified['features'])
    _validate_document('land_price', coverage)
    coverage_ids = {f['id'] for f in coverage['features']}
    assert len(coverage_ids) == len(coverage['features'])
    city = unary_union([shape(f['geometry']) for f in read_json(root / 'inputs/hcmc_expanded_boundary.geojson')['features']])
    prepared_city = prep(city)
    coverage_by_way = {f['properties']['osm_way_ids'][0]: f for f in coverage['features']}
    eligible_ids = set()
    for w in read_json(root / 'raw/land_price/osm_roads.json')['elements']:
        if w.get('type') != 'way' or len(w.get('geometry', [])) < 2:
            continue
        native = LineString([(p['lon'], p['lat']) for p in w['geometry']])
        expected = native if prepared_city.covers(native) else native.intersection(city)
        pieces = line_parts(expected)
        if not pieces:
            continue
        eligible_ids.add(w['id'])
        assert w['id'] in coverage_by_way
        assert shape(coverage_by_way[w['id']]['geometry']).equals(unary_union(pieces))
    assert eligible_ids == coverage_by_way.keys()
    for identifier, f in mapped.items():
        assert all(f['properties'][c+'_vnd_m2'] == rows[identifier][c+'_1000_vnd_m2'] * 1000 for c in CATEGORIES)
        assert shape(f['geometry']).is_valid and not shape(f['geometry']).is_empty
        if f['properties'].get('matcher_version') == 'automatic-reference-fill-v1':
            assert f['geometry'] == coverage_by_way[f['properties']['osm_way_ids'][0]]['geometry']
    for f in coverage['features']:
        original = rows[f['properties']['price_record_id']]
        assert all(f['properties'][c+'_vnd_m2'] == original[c+'_1000_vnd_m2'] * 1000 for c in CATEGORIES)
        assert f['properties']['geometry_reviewed'] is False
    report = dict(verified=True, source_rows=len(rows), goal_rows=len(goal), goal_mapped=len(goal & mapped.keys()),
        goal_pending=0, all_pdf_prices_preserved=True, prior_segments_unchanged=len(verified['features']),
        all_sourced_city_roads_priced=len(eligible_ids), coverage_geometry_equals_actual_source=True,
        placement_policy='automatic-reference-fill-v1')
    if args.api:
        os.environ['DATA_DIR'] = str(snapshot.resolve())
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as client:
            response = client.get('/api/v1/land-prices/catalog?limit=10000&include_geometry=true')
            assert response.status_code == 200
            body = response.json()
            assert body['source_count'] == body['mapped_count'] == len(rows) and body['pending_count'] == 0
            actual = {r['id']: r for r in body['records']}
            assert actual.keys() == mapped.keys()
            assert all(actual[k]['geometry'] == mapped[k]['geometry'] for k in mapped)
            page_ids = []
            for offset in range(0,len(rows),1000):
                page = client.get(f'/api/v1/land-prices/catalog?offset={offset}&limit=1000')
                assert page.status_code == 200
                page_ids.extend(r['id'] for r in page.json()['records'])
            assert page_ids == [r['id'] for r in source['records']]
            layer = client.get('/api/v1/land-prices?limit=10000')
            assert layer.status_code == 200 and len(layer.json()['features']) == min(10000,len(eligible_ids))
            report['complete_catalogue_and_pagination_api_verified'] = True
            report['map_api_verified'] = True
    paths = ['review/land_price_rows.json','raw/land_price/osm_roads.json','inputs/hcmc_expanded_boundary.geojson','inputs/land_price_wards.geojson','review/land_price_pending.baseline_7080.json']
    report['input_sha256'] = {relative:hashlib.sha256((root/relative).read_bytes()).hexdigest() for relative in paths}
    outputs = ['review/land_price_row_matches.geojson','review/land_price_verified_segments.geojson',
               'layers/land_price.geojson','review/land_price_pending.json','review/land_price_catalog.json',
               'review/land_price_automatic_fill_report.json']
    report['snapshot_sha256'] = {relative:hashlib.sha256((snapshot/relative).read_bytes()).hexdigest() for relative in outputs}
    write_json(snapshot/'review/land_price_automatic_verification.json',report)
    print(json.dumps(report))


if __name__ == '__main__':
    main()
