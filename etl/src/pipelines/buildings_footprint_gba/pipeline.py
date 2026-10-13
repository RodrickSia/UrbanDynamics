"""Full extract-transform-load workflow for GBA LoD1 building models."""

import logging
from pathlib import Path

from src.pipelines.buildings_footprint_gba import extract, load, transform
from src.pipelines.buildings_footprint_gba.config import GBABuildingsConfig, config

logger = logging.getLogger(__name__)


def run(
    source: str | Path | None = None,
    refresh: bool = False,
    settings: GBABuildingsConfig = config,
) -> int:
    """Fetch the GBA HCMC tile, clip and enrich it, then publish to PostGIS."""
    polygons, _heights = extract.run(settings, refresh=refresh)
    normalized = transform.run(source or polygons, settings)
    count = load.run(normalized, settings)
    logger.info("GBA LoD1 pipeline finished: %s HCMC buildings", count)
    return count
