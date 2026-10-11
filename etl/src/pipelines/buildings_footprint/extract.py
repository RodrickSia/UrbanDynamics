"""Read the pinned Overture building release for the HCMC bounding box."""

import logging
from pathlib import Path

from src.pipelines.buildings_footprint.config import BuildingsFootprintConfig, config

logger = logging.getLogger(__name__)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run(settings: BuildingsFootprintConfig = config, refresh: bool = False) -> Path:
    """Extract candidate footprints to a local GeoParquet cache.

    The bbox is a source-side prefilter; ``transform`` clips the candidates to
    the pinned post-2025 HCMC boundary before they reach PostGIS.
    """
    import duckdb

    source = settings.overture_buildings_path
    destination = settings.raw_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size and not refresh:
        logger.info("Using cached Overture release %s: %s", settings.overture_release, destination)
        return destination

    west, south, east, north = settings.bbox
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    logger.info(
        "Extracting Overture buildings release %s for HCMC bounds %.6f,%.6f,%.6f,%.6f",
        settings.overture_release,
        west,
        south,
        east,
        north,
    )

    connection = duckdb.connect()
    try:
        connection.execute("LOAD httpfs")
        connection.execute("LOAD spatial")
        connection.execute("SET s3_region = 'us-west-2'")
        connection.execute("SET enable_geoparquet_conversion = true")
        connection.execute(
            f"""
            COPY (
                SELECT
                    id,
                    geometry,
                    names.primary AS name,
                    subtype,
                    "class" AS building_class,
                    has_parts,
                    level,
                    height,
                    num_floors,
                    num_floors_underground,
                    min_height,
                    is_underground,
                    roof_height,
                    sources
                FROM read_parquet(
                    {_literal(source)},
                    hive_partitioning = true,
                    union_by_name = true
                )
                WHERE bbox.xmin <= {east}
                  AND bbox.xmax >= {west}
                  AND bbox.ymin <= {north}
                  AND bbox.ymax >= {south}
            ) TO {_literal(str(temporary))}
            (FORMAT PARQUET, COMPRESSION ZSTD)
            """
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("Overture query produced no candidate building data")
        count = connection.execute(
            f"SELECT count(*) FROM read_parquet({_literal(str(temporary))})"
        ).fetchone()[0]
        if count == 0:
            raise RuntimeError("No Overture buildings intersect the HCMC bounding box")
        temporary.replace(destination)
    except Exception:
        logger.exception("Overture building-footprint extraction failed")
        temporary.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    logger.info(
        "Cached %s Overture candidate footprints at %s (%.1f MiB)",
        count,
        destination,
        destination.stat().st_size / 1024 / 1024,
    )
    return destination
