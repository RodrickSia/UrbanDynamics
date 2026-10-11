"""Bulk-load a clipped GeoParquet snapshot into the dedicated PostGIS table."""

import json
import logging
from pathlib import Path

from psycopg.types.json import Jsonb

from src.pipelines.buildings_footprint.config import BuildingsFootprintConfig, config
from src.shared.database import connect_to_warehouse

logger = logging.getLogger(__name__)


def run(
    source: str | Path | None = None,
    settings: BuildingsFootprintConfig = config,
) -> int:
    """Stream the complete snapshot and atomically replace prior footprints."""
    import duckdb

    source_path = Path(source) if source else settings.normalized_path
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise FileNotFoundError(f"Normalized building Parquet is missing: {source_path}")

    reader = duckdb.connect()
    try:
        cursor = reader.execute(
            "SELECT overture_id, geometry_wkb, properties_json "
            f"FROM read_parquet({_literal(str(source_path))})"
        )
        connection = connect_to_warehouse()
        try:
            with connection:
                connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("hcmc",))
                connection.execute(
                    """
                    CREATE TEMP TABLE buildings_footprint_stage (
                        overture_id TEXT NOT NULL,
                        geometry_wkb BYTEA NOT NULL,
                        properties JSONB NOT NULL
                    ) ON COMMIT DROP
                    """
                )
                copied = 0
                while rows := cursor.fetchmany(settings.batch_size):
                    with connection.cursor().copy(
                        "COPY buildings_footprint_stage "
                        "(overture_id, geometry_wkb, properties) FROM STDIN"
                    ) as copy:
                        for overture_id, geometry_wkb, properties_json in rows:
                            properties = json.loads(properties_json)
                            copy.write_row((overture_id, geometry_wkb, Jsonb(properties)))
                    copied += len(rows)
                    if copied % (settings.batch_size * 10) == 0:
                        logger.info("Staged %s building footprints", copied)

                if copied == 0:
                    raise ValueError("Refusing to replace the building snapshot with zero features")

                connection.execute("TRUNCATE TABLE buildings.footprint")
                connection.execute(
                    """
                    INSERT INTO buildings.footprint (
                        overture_id, source_release, properties, geom, loaded_at
                    )
                    SELECT
                        overture_id,
                        %s,
                        properties,
                        ST_Multi(
                            ST_CollectionExtract(
                                ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(geometry_wkb), 4326)), 3
                            )
                        ),
                        now()
                    FROM buildings_footprint_stage
                    """,
                    (settings.overture_release,),
                )
                actual = connection.execute(
                    "SELECT count(*) FROM buildings.footprint"
                ).fetchone()[0]
                if actual != copied:
                    raise RuntimeError(f"Loaded {actual} footprints; expected {copied}")
                connection.execute(
                    """
                    INSERT INTO buildings.snapshot_metadata (
                        dataset, source_release, source_url, boundary_source, feature_count, loaded_at
                    ) VALUES ('hcmc', %s, %s, %s, %s, now())
                    ON CONFLICT (dataset) DO UPDATE SET
                        source_release = EXCLUDED.source_release,
                        source_url = EXCLUDED.source_url,
                        boundary_source = EXCLUDED.boundary_source,
                        feature_count = EXCLUDED.feature_count,
                        loaded_at = now()
                    """,
                    (
                        settings.overture_release,
                        settings.overture_buildings_path,
                        settings.boundary_source,
                        actual,
                    ),
                )
        finally:
            connection.close()
    finally:
        reader.close()

    logger.info("Replaced HCMC building snapshot with %s Overture footprints", copied)
    return copied


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
