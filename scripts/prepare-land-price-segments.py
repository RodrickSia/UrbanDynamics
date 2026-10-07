"""Prepare spatially checked land-price segments across expanded HCMC."""
import argparse
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'etl' if (ROOT/'etl').is_dir() else ROOT))
from src.shared.data_io import data_dir, write_json
from src.pipelines.land_price.extract import run as extract
from src.pipelines.land_price.road_sources import prepare
from src.pipelines.land_price.road_matcher import match


def run(cached=False, boundary=None, source=None):
    rows, _ = extract(source, full_city=True)
    write_json(data_dir()/'review/land_price_rows.json', rows)
    roads, wards = prepare(Path(boundary) if boundary else None, cached=cached)
    automatic, pending = match(rows, roads, wards)
    write_json(data_dir()/'review/land_price_auto_segments.geojson', automatic)
    write_json(data_dir()/'review/land_price_spatial_pending.json', {'pending':pending,'metadata':automatic['metadata']})
    print(json.dumps(automatic['metadata'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cached', action='store_true', help='Reuse downloaded roads and ward batches')
    parser.add_argument('--boundary')
    parser.add_argument('--source', help='Optional explicit PDF/JSON price source')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run(args.cached, args.boundary, args.source)