"""Load WorldPop GeoTIFFs into the PostGIS raster table."""

import logging
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from psycopg import sql

from src.pipelines.population_hcmc.config import PopulationHCMCConfig, config
from src.shared.database import WarehouseConfig, connect_to_warehouse

logger = logging.getLogger(__name__)


def run(
    normalized_data: Mapping[int, Path],
    settings: PopulationHCMCConfig = config,
) -> None:
    """Import each year's GeoTIFF as tiled PostGIS raster data.

    ``raster2pgsql`` decodes the GeoTIFF client-side, avoiding a dependency on
    GDAL drivers within the PostgreSQL server. Tiles are first loaded to an
    isolated staging table, then copied to the application table with metadata.
    """
    if not normalized_data:
        raise ValueError("No population rasters were provided to the loader")
    for year, raster_path in normalized_data.items():
        path = Path(raster_path)
        if not isinstance(year, int) or not 1900 <= year <= 2200:
            raise ValueError(f"Invalid population raster year: {year!r}")
        if not path.is_file():
            raise FileNotFoundError(f"Population raster for {year} not found: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"Population raster for {year} is empty: {path}")

    table = sql.SQL("{}.{}").format(
        sql.Identifier(settings.database_schema),
        sql.Identifier(settings.raster_table),
    )
    delete_query = sql.SQL("DELETE FROM {} WHERE year = %s").format(table)
    connection_settings = WarehouseConfig.from_env()
    connection = connect_to_warehouse()
    try:
        for year, raster_path in sorted(normalized_data.items()):
            path = Path(raster_path)
            stage_name = f"population_raster_import_{uuid4().hex}"
            stage_table = sql.SQL("{}.{}").format(
                sql.Identifier(settings.database_schema),
                sql.Identifier(stage_name),
            )
            insert_query = sql.SQL(
                """
                INSERT INTO {} (year, source_file, tile_index, rast)
                SELECT %s, %s, ROW_NUMBER() OVER (ORDER BY rid), rast
                FROM {}
                """
            ).format(table, stage_table)

            logger.info("Loading population raster for %s from %s", year, path)
            _import_to_staging_table(path, stage_name, settings, connection_settings)
            try:
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute(delete_query, (year,))
                    cursor.execute(insert_query, (year, path.name))
                    tile_count = cursor.rowcount
            finally:
                with connection.cursor() as cursor:
                    cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(stage_table))
                connection.commit()

            logger.info(
                "Loaded %s PostGIS raster tiles for %s (%s)",
                tile_count,
                year,
                path.name,
            )
    finally:
        connection.close()


def _import_to_staging_table(
    raster_path: Path,
    stage_name: str,
    settings: PopulationHCMCConfig,
    connection_settings: WarehouseConfig,
) -> None:
    """Run raster2pgsql and psql as a streaming client-side raster import."""
    environment = {
        **os.environ,
        "PGHOST": connection_settings.host,
        "PGPORT": str(connection_settings.port),
        "PGDATABASE": connection_settings.database,
        "PGUSER": connection_settings.user,
        "PGPASSWORD": connection_settings.password,
    }
    raster_import = subprocess.Popen(
        [
            "raster2pgsql",
            "-d",
            "-t",
            f"{settings.raster_tile_width}x{settings.raster_tile_height}",
            str(raster_path),
            f"{settings.database_schema}.{stage_name}",
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert raster_import.stdout is not None
    database_import = subprocess.run(
        ["psql", "--quiet", "--set", "ON_ERROR_STOP=1"],
        env=environment,
        stdin=raster_import.stdout,
        capture_output=True,
        text=True,
        check=False,
    )
    raster_import.stdout.close()
    raster_errors = raster_import.communicate()[1].decode().strip()
    if raster_import.returncode or database_import.returncode:
        messages = [
            message
            for message in (raster_errors, database_import.stderr.strip())
            if message
        ]
        detail = "\n".join(messages) or "unknown raster import error"
        raise RuntimeError(f"Could not import {raster_path.name}: {detail}")
