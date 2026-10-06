from src.shared.data_io import data_dir, read_json, write_json
from . import extract, transform, load, unmatched_rows
def run(source=None, segments=None, **kwargs):
    rows, provenance = extract.run(source)
    write_json(data_dir() / "review" / "land_price_rows.json", rows)
    geometry = read_json(segments) if segments else {"features": []}
    document, matched = transform.run(rows, geometry)
    document["metadata"]["provenance"] = provenance
    unmatched_rows.run(rows["records"], matched, data_dir() / "review" / "land_price_pending.json")
    return load.run(document)
