"""Full extract-transform-load workflow for expanded HCMC building footprints."""

import logging
from pathlib import Path

from src.pipelines.buildings_footprint import extract, load, transform
from src.pipelines.buildings_footprint.config import BuildingsFootprintConfig, config

logger = logging.getLogger(__name__)


def run(
    source: str | Path | None = None,
    refresh: bool = False,
    settings: BuildingsFootprintConfig = config,
) -> int:
    """Fetch/cache candidates, clip them to HCMC, and load the DB snapshot."""
    candidate_path = Path(source) if source else extract.run(settings, refresh=refresh)
    normalized_path = transform.run(candidate_path, settings)
    count = load.run(normalized_path, settings)
    logger.info("Buildings-footprint pipeline finished: %s features", count)
    return count
