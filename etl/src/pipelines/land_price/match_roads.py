"""Only exact, manually reviewed segment IDs are eligible for publication."""
from shapely.geometry import shape

def reviewed_segments(document):
    segments = {}
    for feature in document.get("features", []):
        properties = feature["properties"]
        if properties.get("reviewed") is not True:
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
