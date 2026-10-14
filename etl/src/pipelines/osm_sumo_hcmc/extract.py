"""Download the Geofabrik Vietnam extract and crop it to HCMC's road AOI."""

import logging
import subprocess
from pathlib import Path

import requests

from src.pipelines.osm_sumo_hcmc.config import OsmSumoConfig, config

logger = logging.getLogger(__name__)


def run(settings: OsmSumoConfig = config, refresh: bool = False) -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    source = settings.data_dir / "vietnam-latest.osm.pbf"
    cropped = settings.data_dir / "hcmc.osm.pbf"

    # A committed HCMC crop is sufficient for the pipeline; downloading the
    # much larger Vietnam extract is only needed when generating a fresh crop.
    if cropped.is_file() and not refresh:
        logger.info("Using cached HCMC OSM extract at %s", cropped)
        return cropped

    temporary = source.with_suffix(".osm.pbf.part")
    if refresh or not source.exists():
        logger.info("Downloading OSM extract from %s", settings.pbf_url)
        with requests.get(settings.pbf_url, stream=True, timeout=(30, 300)) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        output.write(chunk)
        temporary.replace(source)

    if not cropped.exists() or cropped.stat().st_mtime < source.stat().st_mtime:
        bounds = f"{settings.west},{settings.south},{settings.east},{settings.north}"
        subprocess.run(
            ["osmium", "extract", "--overwrite", "-b", bounds, str(source), "-o", str(cropped)],
            check=True,
        )
    logger.info("HCMC OSM extract ready at %s", cropped)
    return cropped
