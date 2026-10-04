"""Download the configured WorldPop population rasters."""

import logging
import re
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.pipelines.population_hcmc.config import PopulationHCMCConfig, config

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024
PROGRESS_INTERVAL = 25 * 1024 * 1024


def _open_from_offset(url: str, offset: int):
    request = Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
    try:
        return urlopen(request, timeout=60)
    except HTTPError as error:
        # A stale or already-complete partial file can make a server return 416.
        if offset and error.code == 416:
            logger.warning("Server rejected resume offset; restarting %s", url)
            error.close()
            return urlopen(Request(url), timeout=60)
        raise


def download_population_raster(url: str, destination: Path) -> Path:
    """Stream a raster to disk, resuming a previous partial download when possible."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        logger.info("Using existing raster: %s", destination)
        return destination

    temporary_path = destination.with_suffix(destination.suffix + ".part")
    offset = temporary_path.stat().st_size if temporary_path.exists() else 0
    started_at = monotonic()
    if offset:
        logger.info("Resuming %s at %.1f MiB", destination.name, offset / (1024 * 1024))
    else:
        logger.info("Starting download: %s", destination.name)

    try:
        response = _open_from_offset(url, offset)
        with response:
            # Append only when the server honored the Range request. If it returned
            # a full response (200), restart the partial file instead of duplicating it.
            append = offset > 0 and getattr(response, "status", None) == 206
            if offset and not append:
                logger.warning("Server does not support resume; restarting %s", destination.name)
                offset = 0

            content_range = response.headers.get("Content-Range", "")
            match = re.search(r"/(\d+)$", content_range)
            total_bytes = int(match.group(1)) if match else None
            if total_bytes is None:
                length = response.headers.get("Content-Length")
                total_bytes = offset + int(length) if length else None

            mode = "ab" if append else "wb"
            downloaded = offset
            next_report = downloaded + PROGRESS_INTERVAL
            logger.info(
                "Downloading %s (%.1f MiB%s)",
                destination.name,
                downloaded / (1024 * 1024),
                f" of {total_bytes / (1024 * 1024):.1f} MiB" if total_bytes else "",
            )
            with temporary_path.open(mode) as output:
                while chunk := response.read(CHUNK_SIZE):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_report:
                        logger.info(
                            "%s: %.1f MiB%s",
                            destination.name,
                            downloaded / (1024 * 1024),
                            f" / {total_bytes / (1024 * 1024):.1f} MiB" if total_bytes else "",
                        )
                        next_report = downloaded + PROGRESS_INTERVAL

        if temporary_path.stat().st_size == 0:
            raise RuntimeError(f"WorldPop returned an empty file for {url}")
        temporary_path.replace(destination)
    except Exception:
        logger.exception("Download failed for %s; partial data is kept at %s", destination.name, temporary_path)
        raise

    elapsed = monotonic() - started_at
    size_mb = destination.stat().st_size / (1024 * 1024)
    logger.info("Finished %s (%.1f MiB, %.1fs)", destination.name, size_mb, elapsed)
    return destination


def run(settings: PopulationHCMCConfig = config) -> dict[int, Path]:
    """Download all configured years and return paths keyed by year."""
    downloaded: dict[int, Path] = {}
    for year, source_url in sorted(settings.worldpop.population_paths.items()):
        destination = settings.download_dir / f"worldpop_hcmc_{year}.tif"
        logger.info("Processing WorldPop year %s", year)
        downloaded[year] = download_population_raster(str(source_url), destination)
    return downloaded
