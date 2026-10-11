"""Download the pinned GBA tile files with resumable progress reporting."""

import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.pipelines.buildings_footprint_gba.config import GBABuildingsConfig, config

logger = logging.getLogger(__name__)


def _session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET",)),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "UrbanDynamics-ETL/1.0"})
    return session


def _download(url: str, destination: Path, settings: GBABuildingsConfig) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    existing_size = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={existing_size}-"} if existing_size else {}
    timeout = (settings.timeout_connect_seconds, settings.timeout_read_seconds)
    logger.info(
        "Downloading %s to %s (resume offset: %.2f GiB)",
        url,
        destination,
        existing_size / 1024**3,
    )

    with _session().get(url, headers=headers, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        if existing_size and response.status_code == 206:
            mode = "ab"
            downloaded = existing_size
            range_header = response.headers.get("Content-Range", "")
            total_size = (
                int(range_header.rsplit("/", 1)[-1]) if "/" in range_header else None
            )
        else:
            mode = "wb"
            downloaded = 0
            existing_size = 0
            total_size = (
                int(response.headers["Content-Length"])
                if response.headers.get("Content-Length")
                else None
            )
        next_log = downloaded + settings.log_interval_bytes
        if total_size:
            logger.info("Source size: %.2f GiB", total_size / 1024**3)
        with partial.open(mode) as output:
            for chunk in response.iter_content(chunk_size=4 * 1024 * 1024):
                if not chunk:
                    continue
                output.write(chunk)
                downloaded += len(chunk)
                if downloaded >= next_log:
                    if total_size:
                        logger.info(
                            "Downloaded %.2f / %.2f GiB (%.1f%%)",
                            downloaded / 1024**3,
                            total_size / 1024**3,
                            downloaded * 100 / total_size,
                        )
                    else:
                        logger.info("Downloaded %.2f GiB", downloaded / 1024**3)
                    next_log = downloaded + settings.log_interval_bytes

    if total_size is not None and downloaded != total_size:
        raise OSError(
            f"Incomplete download for {url}: got {downloaded} of {total_size} bytes"
        )
    partial.replace(destination)
    logger.info("Downloaded %.2f GiB to %s", downloaded / 1024**3, destination)
    return destination


def run(
    settings: GBABuildingsConfig = config, refresh: bool = False
) -> tuple[Path, Path]:
    """Cache polygon and height source files for the HCMC GBA tile."""
    paths = (
        (settings.polygon_url, settings.polygon_path),
        (settings.heights_url, settings.heights_path),
    )
    results = []
    for url, destination in paths:
        if destination.is_file() and destination.stat().st_size and not refresh:
            logger.info(
                "Using cached GBA source: %s (%.2f GiB)",
                destination,
                destination.stat().st_size / 1024**3,
            )
            results.append(destination)
            continue
        if refresh:
            destination.unlink(missing_ok=True)
            destination.with_suffix(destination.suffix + ".part").unlink(
                missing_ok=True
            )
        results.append(_download(url, destination, settings))
    return results[0], results[1]
