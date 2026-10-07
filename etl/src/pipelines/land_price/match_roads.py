"""Validate road geometry approved by a reviewer or the configured auto-matcher."""
from shapely.geometry import shape
from .road_matcher import METHODS, VERSION

def matched_segments(document):
    segments = {}
    for feature in document.get("features", []):
        properties = feature["properties"]
        legacy_auto = (
            properties.get("auto_approved") is True
            and properties.get("match_method") == "exact_normalized_osm_name"
        )
        spatial_auto = (properties.get("auto_approved") is True
                        and properties.get("match_method") in METHODS
                        and properties.get("matcher_version") == VERSION
                        and properties.get("match_confidence") == "spatially_checked"
                        and properties.get("ward_osm_relation_id") is not None)
        auto_approved = legacy_auto or spatial_auto
        if properties.get("reviewed") is not True and not auto_approved:
            continue
        key = properties.get("price_record_id")
        if not key or key in segments:
            raise ValueError("Reviewed segments need unique price_record_id")
        geometry = shape(feature["geometry"])
        if geometry.geom_type not in ("LineString", "MultiLineString") or not geometry.is_valid or geometry.is_empty:
            raise ValueError("Reviewed road segment must be a valid line")
        if not (-180 <= geometry.bounds[0] <= geometry.bounds[2] <= 180
                and -90 <= geometry.bounds[1] <= geometry.bounds[3] <= 90):
            raise ValueError("Reviewed road segment must use WGS84")
        segments[key] = feature
    return segments
