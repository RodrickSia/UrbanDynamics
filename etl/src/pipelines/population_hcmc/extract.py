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


def _sql_string(value: str) -> str:
    """Quote a string literal for the fixed DuckDB query templates below."""
    return "'" + value.replace("'", "''") + "'"


def fetch_overture_buildings(settings: PopulationHCMCConfig) -> Path:
    """Query the pinned Overture release and save buildings inside HCMC."""
    import duckdb

    source = settings.overture
    destination = source.buildings_output_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        logger.info("Using existing Overture extract: %s", destination)
        return destination

    west, south, east, north = source.search_bbox
    boundary_path = _sql_string(source.division_areas_path)
    buildings_path = _sql_string(source.buildings_path)
    city_name = _sql_string(source.city_name)
    country_code = _sql_string(source.country_code)
    boundary_filter = f"""
        country = {country_code}
        AND subtype = 'region'
        AND names.primary = {city_name}
        AND is_land = TRUE
        AND bbox.xmin <= {east}
        AND bbox.xmax >= {west}
        AND bbox.ymin <= {north}
        AND bbox.ymax >= {south}
    """

    logger.info(
        "Finding the %s boundary in Overture release %s",
        source.city_name,
        source.release,
    )
    connection = duckdb.connect()
    try:
        connection.execute("LOAD httpfs")
        connection.execute("LOAD spatial")
        connection.execute("SET s3_region = 'us-west-2'")
        connection.execute("SET enable_geoparquet_conversion = true")

        boundary_count = connection.execute(
            f"""
            SELECT count(*)
            FROM read_parquet({boundary_path}, hive_partitioning = true)
            WHERE {boundary_filter}
            """
        ).fetchone()[0]
        if not boundary_count:
            raise RuntimeError(
                f"No land boundary found for {source.city_name!r} "
                f"in Overture release {source.release}"
            )

        temporary_path = destination.with_suffix(destination.suffix + ".part")
        temporary_path.unlink(missing_ok=True)
        logger.info(
            "Querying Overture buildings in bbox %.4f,%.4f,%.4f,%.4f; "
            "the city polygon applies the exact boundary filter",
            west,
            south,
            east,
            north,
        )
        connection.execute(
            f"""
            COPY (
                WITH hcmc AS (
                    SELECT ST_Union_Agg(geometry) AS geometry
                    FROM read_parquet({boundary_path}, hive_partitioning = true)
                    WHERE {boundary_filter}
                ),
                candidate_buildings AS (
                    SELECT *
                    FROM read_parquet(
                        {buildings_path},
                        hive_partitioning = true,
                        union_by_name = true
                    )
                    WHERE bbox.xmin <= {east}
                      AND bbox.xmax >= {west}
                      AND bbox.ymin <= {north}
                      AND bbox.ymax >= {south}
                )
                SELECT buildings.*
                FROM candidate_buildings AS buildings
                CROSS JOIN hcmc
                WHERE ST_Intersects(buildings.geometry, hcmc.geometry)
            ) TO {_sql_string(str(temporary_path))}
            (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        if not temporary_path.exists() or temporary_path.stat().st_size == 0:
            raise RuntimeError("DuckDB did not produce an Overture buildings extract")
        temporary_path.replace(destination)
    except Exception:
        logger.exception("Overture buildings extraction failed")
        raise
    finally:
        connection.close()

    logger.info(
        "Saved HCMC Overture buildings to %s (%.1f MiB)",
        destination,
        destination.stat().st_size / (1024 * 1024),
    )
    return destination


def run(settings: PopulationHCMCConfig = config) -> dict[str, object]:
    """Download WorldPop rasters and the Overture HCMC buildings extract."""
    downloaded: dict[int, Path] = {}
    for year, source_url in sorted(settings.worldpop.population_paths.items()):
        destination = settings.download_dir / f"worldpop_hcmc_{year}.tif"
        logger.info("Processing WorldPop year %s", year)
        downloaded[year] = download_population_raster(str(source_url), destination)
    overture_buildings = fetch_overture_buildings(settings)
    return {"worldpop": downloaded, "overture_buildings": overture_buildings}
