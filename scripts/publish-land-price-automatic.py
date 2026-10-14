"""Publish an already verified automatic allocation without rerunning matching."""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'etl'))
from src.shared.data_io import read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-dir', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'etl/data')
    parser.add_argument('--mirror-dir', type=Path)
    parser.add_argument('--warehouse', action='store_true')
    args = parser.parse_args()
    snapshot = args.snapshot_dir
    report = read_json(snapshot/'review/land_price_automatic_verification.json')
    if report.get('verified') is not True or report.get('goal_mapped') != 7080 or report.get('goal_pending') != 0:
        raise ValueError('Complete automatic snapshot verification is required')
    for relative, expected in report['snapshot_sha256'].items():
        if hashlib.sha256((snapshot/relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Snapshot changed after verification: {relative}')
    destinations = [args.data_dir] + ([args.mirror_dir] if args.mirror_dir else [])
    for root in destinations:
        for relative, expected in report['input_sha256'].items():
            if hashlib.sha256((root/relative).read_bytes()).hexdigest() != expected:
                raise ValueError(f'Source changed after verification: {root/relative}')
    public = list(report['snapshot_sha256']) + ['review/land_price_automatic_verification.json']
    for root in destinations:
        backup = snapshot/'prepublication-backup'/(root.name+'-'+hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:8])
        for relative in public + ['review/land_price_review_summary.json','review/land_price_review_ledger.json']:
            original = root/relative
            saved = backup/relative
            if original.exists() and not saved.exists():
                saved.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(original,saved)
        for relative in public:
            write_json(root/relative,read_json(snapshot/relative))
        metadata = read_json(snapshot/'layers/land_price.geojson')['metadata']
        write_json(root/'review/land_price_review_summary.json', metadata)
        source = read_json(root/'review/land_price_rows.json')
        write_json(root/'review/land_price_review_ledger.json', {'metadata':metadata,
            'records':[{'id':r['id'],'decision':'automatic_reference_allocation','source_row':r}
                       for r in source['records']]})
    if args.warehouse:
        from src.shared.database import publish
        print(publish('land_price',read_json(snapshot/'layers/land_price.geojson'),root=args.data_dir))
    print({'published_to':[str(r) for r in destinations],'goal_mapped':report['goal_mapped'],
           'roads_with_price':report['all_sourced_city_roads_priced'],'warehouse_published':args.warehouse})


if __name__ == '__main__':
    main()
