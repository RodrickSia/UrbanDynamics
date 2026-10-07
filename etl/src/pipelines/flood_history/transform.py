import math
import hashlib
import re
import unicodedata
from dataclasses import asdict
import pandas as pd
from shapely.geometry import mapping
from shapely import force_2d
from src.shared.data_io import collection
from src.shared.spatial import geographic_frame, read_boundary
from .config import DATASET_URL, LICENSE
from .models import FloodObservation

def normalize(value):
    value = unicodedata.normalize("NFD", str(value)).lower().replace("đ", "d")
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in value if not unicodedata.combining(c)))

def clean(value):
    if value is None or pd.isna(value):
        return None
    return str(value).strip().strip('"') or None

def number(value):
    value = clean(value)
    if value is None:
        return None
    try:
        result = float(value.replace(",", "."))
    except ValueError:
        raise ValueError(f"Invalid depth: {value}") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError("Depth must be finite and nonnegative")
    return result

def transform_frame(frame, boundary=None, scope="HCMC"):
    if frame.crs is None:
        raise ValueError("Flood geometry CRS missing")
    frame = frame.to_crs(4326)
    frame.geometry = frame.geometry.apply(force_2d)
    source_count = len(frame)
    id_column = next((c for c in frame.columns if normalize(c) == "obsid"), None)
    duplicates = set(frame.loc[frame[id_column].duplicated(keep=False),id_column]) if id_column else set()
    if boundary is not None:
        frame = frame[frame.geometry.apply(boundary.covers)]
    aliases = {normalize(c): c for c in frame.columns if c != frame.geometry.name}
    def column(row, *names):
        for name in names:
            key = aliases.get(normalize(name))
            if key:
                return row[key]
        return None
    features = []
    for index, row in frame.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty or not geometry.is_valid or geometry.geom_type != "Point":
            raise ValueError("Historical flood observations must have valid Point geometry")
        identifier = clean(column(row, "Obs_id", "Observation_id", "OBJECTID")) or str(index)
        date = clean(column(row, "Date", "observation_date"))
        parsed = pd.to_datetime(date, dayfirst=not bool(re.match(r"^\d{4}-",date)), errors="coerce") if date else pd.NaT
        if date and pd.isna(parsed):
            raise ValueError(f"Unrecognized observation date: {date}")
        source_identifier = identifier
        if column(row, "Obs_id") in duplicates:
            fingerprint = f"{identifier}|{date}|{column(row,'Year')}|{column(row,'Location name')}|{geometry.wkt}"
            identifier += ":" + hashlib.sha256(fingerprint.encode()).hexdigest()[:12]
        record = FloodObservation(identifier, None if pd.isna(parsed) else parsed.date().isoformat(),
                                  clean(column(row, "Location name", "Location")) or "Unknown",
                                  number(column(row, "Water height min (cm)", "Height_min")),
                                  number(column(row, "Water height max (cm)", "Height_max")),
                                  clean(column(row, "Cause")))
        if record.depth_min_cm is not None and record.depth_max_cm is not None and record.depth_min_cm > record.depth_max_cm:
            raise ValueError(f"Reversed depth range for {identifier}")
        properties = asdict(record)
        properties.update({"source_url": DATASET_URL, "license": LICENSE,
                           "source_observation_id": source_identifier,
                           "year": clean(column(row, "Year")),
                           "spatial_precision": clean(column(row, "Spatial precision")),
                           "geocoding_method": clean(column(row, "Geocoding method")),
                           "depth_class": clean(column(row, "Depth class")),
                           "source_id": clean(column(row, "Source id")),
                           "original_attributes": {str(k): clean(v) for k, v in row.items() if k != frame.geometry.name}})
        features.append({"type": "Feature", "id": identifier, "geometry": mapping(geometry), "properties": properties})
    return collection("flood_history", features, scope=scope, source_url=DATASET_URL, license=LICENSE,
                      source_count=source_count, spatial_count=len(features),
                      limitations="News-derived observations; unreported events are missing. No report does not mean no flooding.")

def run(source, boundary=None):
    scope = 'HCMC (source coverage; no boundary filter)'
    if boundary:
        from src.shared.data_io import read_json
        scope = read_json(boundary).get('metadata',{}).get('scope','Custom boundary-filtered area')
    return transform_frame(geographic_frame(source),read_boundary(boundary) if boundary else None,scope)
