"""Validate that the locally fetched TomTom snapshot is available."""

from pathlib import Path

from src.pipelines.road_data_tomtom.config import TomTomConfig, config


def run(settings: TomTomConfig = config) -> Path:
    if not settings.source_file.is_file():
        raise FileNotFoundError(
            f"TomTom source CSV not found: {settings.source_file}. "
            "Fetch it with scripts/test_tomtom_traffic.py first."
        )
    return settings.source_file
