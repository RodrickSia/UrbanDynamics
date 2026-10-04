from dataclasses import asdict
from src.shared.data_io import collection
from .extract import row_id
from .models import LandPrice
from .match_roads import reviewed_segments

def run(source, segments):
    if source.get("published_unit") != "1000 VND/m2":
        raise ValueError("Explicit published_unit=1000 VND/m2 required")
    matched = reviewed_segments(segments)
    features, matched_ids = [], set()
    seen = set()
    for record in source["records"]:
        identifier = record.get("id") or row_id(record)
        if identifier in seen:
            raise ValueError("Duplicate price rows")
        seen.add(identifier)
        values = [record[k] for k in ("residential_1000_vnd_m2", "commercial_1000_vnd_m2", "other_nonagricultural_1000_vnd_m2")]
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in values):
            raise ValueError("Prices must be positive integers in published units")
        segment = matched.get(identifier)
        if segment is None:
            continue
        # Reviewer must confirm the extracted text/values as well as geometry.
        if record.get("extraction_review_required") and not segment["properties"].get("price_values_reviewed"):
            continue
        model = LandPrice(identifier, record["road"], record["from"], record["to"], *(v*1000 for v in values))
        properties = asdict(model)
        properties.update({"source_url": source["source_url"], "effective_from": source["effective_from"],
                           "unit": "VND/m2", "price_kind": "official_reference", "geometry_reviewed": True,
                           "geometry_coverage": segment["properties"].get("geometry_coverage", "reviewed_published_segment"),
                           "osm_way_ids": segment["properties"].get("osm_way_ids", []),
                           "geometry_source_url": segment["properties"].get("geometry_source_url"),
                           "geometry_license": segment["properties"].get("geometry_license"),
                           "review_note": segment["properties"].get("review_note"),
                           "pdf_page": record.get("pdf_page")})
        features.append({"type": "Feature", "id": identifier, "geometry": segment["geometry"], "properties": properties})
        matched_ids.add(identifier)
    return collection("land_price", features, source_url=source["source_url"], source_rows=len(source["records"]),
                      matched_rows=len(features), pending_rows=len(source["records"])-len(features),
                      effective_from=source["effective_from"], price_kind="official_reference",
                      limitations="Partial manually reviewed road coverage. Not transaction or asking prices."), matched_ids
