from src.shared.data_io import data_dir, read_json, write_json
from . import extract, transform, load, unmatched_rows
def run(source=None, segments=None, full_city=False, refresh_source=False, **kwargs):
    rows, provenance = extract.run(source,full_city=full_city,refresh_source=refresh_source)
    write_json(data_dir() / "review" / "land_price_rows.json", rows)
    geometry = read_json(segments) if segments else {"features": []}
    reasons, matching_metadata = {}, geometry.get('metadata', {})
    if full_city:
        from .road_sources import prepare
        from .road_matcher import match
        roads, wards = prepare(cached=not refresh_source)
        automatic, pending = match(rows, roads, wards)
        write_json(data_dir()/"review/land_price_auto_segments.geojson", automatic)
        # Human-reviewed segments override automatic results. Older name-only
        # proxies must not bypass the citywide spatial checks.
        selected = {f['properties']['price_record_id']:f for f in automatic['features']}
        for feature in geometry.get('features', []):
            if feature['properties'].get('reviewed') is True:
                selected[feature['properties']['price_record_id']] = feature
        geometry = {'features':list(selected.values())}
        reasons = {r['id']:r['unmatched_reason'] for r in pending}
        matching_metadata = automatic['metadata']
    document, matched = transform.run(rows, geometry)
    document["metadata"]["provenance"] = provenance
    document['metadata']['spatial_matching'] = matching_metadata
    unmatched_rows.run(rows["records"], matched, data_dir() / "review" / "land_price_pending.json", reasons)
    return load.run(document)
