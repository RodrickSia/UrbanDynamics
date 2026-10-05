"""Download HCMC land-plot vector tiles, resuming from a local journal."""

import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

import mercantile

from src.pipelines.parcels_hcmc.config import ParcelsHCMCConfig, config

logger = logging.getLogger(__name__)


def _pace(delay_seconds: float, not_before: list[float]) -> None:
    wait = not_before[0] - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    not_before[0] = time.monotonic() + delay_seconds


def _fetch_tile(url: str, settings: ParcelsHCMCConfig, not_before: list[float]) -> bytes | None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": settings.user_agent,
            "Referer": settings.referer,
            "Accept": "*/*",
        },
    )
    last_error: Exception | None = None
    for attempt in range(8):
        _pace(settings.request_delay_seconds, not_before)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                if response.status == 204:
                    return None
                body = response.read()
                return body or None
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code == 204:
                return None
            if error.code not in (429, 500, 502, 503, 504):
                raise
            wait = settings.rate_limit_cooldown_seconds if error.code == 429 else 5.0 * (attempt + 1)
            logger.warning("HTTP %s for %s; waiting %.0fs", error.code, url, wait)
            time.sleep(wait)
        except urllib.error.URLError as error:
            last_error = error
            time.sleep(5.0 * (attempt + 1))
    raise RuntimeError(f"Failed to download {url}: {last_error}")


def run(settings: ParcelsHCMCConfig = config) -> Path:
    """Save zoom-16 parcel tiles under the configured download directory.

    Empty tiles are recorded in ``done.txt`` and not written. A failed tile is
    left out of the journal so the next run retries it. The run fails if any
    tile could not be fetched.
    """
    destination = settings.download_dir
    destination.mkdir(parents=True, exist_ok=True)
    journal_path = destination / "done.txt"
    done = set()
    if journal_path.exists():
        done = {line.strip() for line in journal_path.read_text().splitlines() if line.strip()}

    tiles = list(
        mercantile.tiles(settings.west, settings.south, settings.east, settings.north, zooms=[settings.zoom])
    )
    pending = [tile for tile in tiles if f"{tile.z}/{tile.x}/{tile.y}" not in done]
    logger.info("Parcel tiles: %s total, %s already fetched, %s pending", len(tiles), len(done), len(pending))

    saved = empty = failed = 0
    not_before = [0.0]
    with journal_path.open("a", encoding="utf-8") as journal:
        for index, tile in enumerate(pending, start=1):
            key = f"{tile.z}/{tile.x}/{tile.y}"
            url = settings.tile_url.format(z=tile.z, x=tile.x, y=tile.y)
            try:
                body = _fetch_tile(url, settings, not_before)
            except Exception:
                failed += 1
                logger.exception("Giving up on tile %s", key)
                continue
            if not body:
                empty += 1
            else:
                path = destination / str(tile.z) / str(tile.x) / f"{tile.y}.pbf"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                saved += 1
            journal.write(key + "\n")
            journal.flush()
            if index % 100 == 0 or index == len(pending):
                logger.info(
                    "[%s/%s] saved %s empty %s failed %s",
                    index,
                    len(pending),
                    saved,
                    empty,
                    failed,
                )

    if failed:
        raise RuntimeError(f"{failed} parcel tiles failed; rerun to retry them")
    logger.info("Parcel download finished: saved %s, empty %s", saved, empty)
    return destination
