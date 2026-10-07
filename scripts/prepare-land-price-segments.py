"""Prepare spatially checked land-price segments across expanded HCMC."""
import argparse
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'etl' if (ROOT/'etl').is_dir() else ROOT))
from src.shared.data_io import data_dir, write_json
from src.shared.spatial import read_boundary
from src.pipelines.land_price.extract import run as extract
from src.pipelines.land_price.road_sources import prepare, wards as fetch_wards
from src.pipelines.land_price.road_matcher import match


def run(cached=False, boundary=None, source=None, wards_only=False):
    rows, _ = extract(source, full_city=True)
    write_json(data_dir()/'review/land_price_rows.json', rows)
    if wards_only:
        document = fetch_wards(Path(boundary) if boundary else data_dir()/'inputs/hcmc_expanded_boundary.geojson', cached)
        print(json.dumps({'ward_boundary_count':len(document['features']), **document['metadata']}, ensure_ascii=False))
        return
    roads, wards = prepare(Path(boundary) if boundary else None, cached=cached)
    city = read_boundary(Path(boundary) if boundary else data_dir()/'inputs/hcmc_expanded_boundary.geojson')
    automatic, pending = match(rows, roads, wards, city_geometry=city)
    write_json(data_dir()/'review/land_price_auto_segments.geojson', automatic)
    write_json(data_dir()/'review/land_price_spatial_pending.json', {'pending':pending,'metadata':automatic['metadata']})
    print(json.dumps(automatic['metadata'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cached', action='store_true', help='Reuse downloaded roads and ward batches')
    parser.add_argument('--boundary')
    parser.add_argument('--source', help='Optional explicit PDF/JSON price source')
    parser.add_argument('--wards-only', action='store_true', help='Fetch ward polygons for matching against existing roads elsewhere')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(args.cached, args.boundary, args.source, args.wards_only)
