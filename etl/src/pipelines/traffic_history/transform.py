"""Normalize source traffic rows into stable timestamped observations."""

import csv
import logging
import os
import tempfile
from datetime import datetime, time
from pathlib import Path

from src.pipelines.traffic_history.config import TrafficHistoryConfig, config

logger = logging.getLogger(__name__)

FIELDS = (
    "source_row_id", "source_segment_id", "observed_at", "period_minutes",
    "los", "source_max_velocity", "source_start_node", "source_end_node",
    "source_length_m", "street_id", "street_name", "street_type",
    "start_lon", "start_lat", "end_lon", "end_lat",
)


def _period(value: str) -> time:
    if not value.startswith("period_"):
        raise ValueError(f"Invalid period value {value!r}; expected period_HH_MM")
    hour_text, minute_text = value.removeprefix("period_").split("_", 1)
    hour, minute = int(hour_text), int(minute_text)
    if hour not in range(24) or minute not in (0, 30):
        raise ValueError(f"Invalid 30-minute period {value!r}")
    return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()


def run(source: str | Path | None = None, settings: TrafficHistoryConfig = config) -> Path:
    """Write normalized source data without changing the original CSV."""
    source_path = Path(source) if source else settings.source_file
    output_path = settings.transformed_file
    if not source_path.is_file():
        raise FileNotFoundError(f"Traffic source CSV not found: {source_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    count = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=FIELDS)
            writer.writeheader()
            with source_path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                required = {"_id", "segment_id", "date", "period", "LOS", "s_node_id", "e_node_id", "length", "street_id", "max_velocity", "street_name", "street_type", "long_snode", "lat_snode", "long_enode", "lat_enode"}
                missing = required.difference(reader.fieldnames or ())
                if missing:
                    raise ValueError(f"Traffic CSV is missing required columns: {sorted(missing)}")
                for row in reader:
                    timestamp = datetime.combine(datetime.strptime(row["date"], "%Y-%m-%d").date(), _period(row["period"]))
                    los = row["LOS"].strip().upper()
                    if los not in {"A", "B", "C", "D", "E", "F"}:
                        raise ValueError(f"Invalid LOS {los!r} in source row {row['_id']}")
                    speed = row["max_velocity"].strip()
                    writer.writerow({
                        "source_row_id": row["_id"], "source_segment_id": row["segment_id"],
                        "observed_at": timestamp.isoformat(sep=" "), "period_minutes": 30,
                        "los": los, "source_max_velocity": speed or "",
                        "source_start_node": row["s_node_id"], "source_end_node": row["e_node_id"],
                        "source_length_m": row["length"], "street_id": row["street_id"],
                        "street_name": row["street_name"], "street_type": row["street_type"],
                        "start_lon": row["long_snode"], "start_lat": row["lat_snode"],
                        "end_lon": row["long_enode"], "end_lat": row["lat_enode"],
                    })
                    count += 1
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    logger.info("Normalized %d traffic observations to %s", count, output_path)
    return output_path
