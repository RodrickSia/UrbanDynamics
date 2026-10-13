"""Allocate all cached price rows and fill every sourced city road automatically."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'etl'))
from src.pipelines.land_price.automatic_fill import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'etl/data')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--publish-local', action='store_true')
    parser.add_argument('--publish-warehouse', action='store_true')
    args = parser.parse_args()
    print(run(args.data_dir, args.output_dir, args.publish_local, args.publish_warehouse))
