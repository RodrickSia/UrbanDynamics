from src.shared.data_io import data_dir, read_json, write_json
from . import extract, transform, load, review_matches
def run(source=None, segments=None, full_city=False, refresh_source=False, **kwargs):
    rows, provenance = extract.run(source,full_city=full_city,refresh_source=refresh_source)
    write_json(data_dir() / "review" / "land_price_rows.json", rows)
    geometry = read_json(segments) if segments else {"features": []}
    document, matched = transform.run(rows, geometry)
    document["metadata"]["provenance"] = provenance
    review_matches.run(rows["records"], matched, data_dir() / "review" / "land_price_pending.json")
    return load.run(document)
