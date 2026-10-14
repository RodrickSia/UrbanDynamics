"""Validate, deduplicate tile overlaps, and normalize TomTom flow features."""

import csv
import hashlib
import logging
import os
import tempfile
from pathlib import Path

from src.pipelines.road_data_tomtom.config import TomTomConfig, config

logger = logging.getLogger(__name__)
FIELDS = (
    "source_feature_id", "fetched_at_utc", "fetched_at_hcmc", "time_period_hcmc",
    "tile_zoom", "tile_x", "tile_y", "road_category", "road_subcategory",
    "current_speed_kmh", "relative_speed", "road_closure",
    "part_of_two_way_road", "openlr", "geometry_wkt",
)
REQUIRED = {"fetched_at_utc", "geometry_wkt", "current_speed_kmh", "relative_speed"}


def run(source: str | Path | None = None, settings: TomTomConfig = config) -> Path:
    source_path = Path(source) if source else settings.source_file
    if not source_path.is_file():
        raise FileNotFoundError(f"TomTom source CSV not found: {source_path}")
    output = settings.transformed_file
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix=".tmp")
    seen: set[str] = set()
    count = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=FIELDS)
            writer.writeheader()
            with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                missing = REQUIRED.difference(reader.fieldnames or ())
                if missing:
                    raise ValueError(f"TomTom CSV is missing required columns: {sorted(missing)}")
                for row in reader:
                    geometry = (row.get("geometry_wkt") or "").strip()
                    captured = (row.get("fetched_at_utc") or "").strip()
                    if not geometry.startswith(("LINESTRING(", "MULTILINESTRING(")) or not captured:
                        continue
                    signature = hashlib.sha256(
                        f"{captured}|{row.get('openlr', '')}|{geometry}".encode()
                    ).hexdigest()
                    if signature in seen:
                        continue
                    seen.add(signature)
                    row["source_feature_id"] = signature
                    writer.writerow({name: row.get(name, "") for name in FIELDS})
                    count += 1
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    logger.info("Normalized %d unique TomTom flow segments to %s", count, output)
    return output
