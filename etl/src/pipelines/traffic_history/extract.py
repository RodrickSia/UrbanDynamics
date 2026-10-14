"""Validate the checked-in historical traffic source file."""

from pathlib import Path

from src.pipelines.traffic_history.config import TrafficHistoryConfig, config


def run(settings: TrafficHistoryConfig = config) -> Path:
    if not settings.source_file.is_file():
        raise FileNotFoundError(f"Traffic source CSV not found: {settings.source_file}")
    return settings.source_file
