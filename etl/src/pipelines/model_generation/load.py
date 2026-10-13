"""Atomically replace the generated residential building snapshot in PostGIS."""

import json
import logging

from src.pipelines.model_generation.config import ModelGenerationConfig, config
from src.shared.data_io import data_dir
from src.shared.database import connect_to_warehouse

logger = logging.getLogger(__name__)


def run(settings: ModelGenerationConfig = config) -> int:
    root = data_dir() / settings.data_dir.name
    source_path = root / "synthetic_buildings.jsonl"
    manifest_path = root / "manifest.json"
    if not source_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Run model_generation transform before load")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = int(manifest["generated_count"])
    connection = connect_to_warehouse()
    try:
        with connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                ("synthetic-residential-buildings",),
            )
            connection.execute(
                """CREATE TEMP TABLE synthetic_buildings_stage (
                     parcel_id BIGINT NOT NULL,
                     mdsdd TEXT NOT NULL,
                     height_m DOUBLE PRECISION NOT NULL,
                     floors SMALLINT NOT NULL,
                     inset_m DOUBLE PRECISION NOT NULL,
                     height_source TEXT NOT NULL,
                     geometry_json JSONB NOT NULL
                   ) ON COMMIT DROP"""
            )
            copied = 0
            with source_path.open(encoding="utf-8") as source:
                with connection.cursor().copy(
                    """COPY synthetic_buildings_stage
                       (parcel_id, mdsdd, height_m, floors, inset_m, height_source, geometry_json)
                       FROM STDIN"""
                ) as copy:
                    for line in source:
                        model = json.loads(line)
                        copy.write_row(
                            (
                                model["parcel_id"],
                                model["mdsdd"],
                                model["height_m"],
                                model["floors"],
                                model["inset_m"],
                                model["height_source"],
                                json.dumps(model["geometry"], allow_nan=False),
                            )
                        )
                        copied += 1
            if copied != expected:
                raise RuntimeError(
                    f"Transformed model count {copied} does not match manifest {expected}"
                )
            connection.execute("DELETE FROM buildings.synthetic_residential")
            connection.execute(
                """INSERT INTO buildings.synthetic_residential (
                     parcel_id, mdsdd, geom, height_m, floors, inset_m,
                     height_source, generator_version, generated_at
                   )
                   SELECT parcel_id, mdsdd,
                     ST_Multi(ST_CollectionExtract(ST_MakeValid(
                       ST_SetSRID(ST_GeomFromGeoJSON(geometry_json::text), 4326)
                     ), 3)),
                     height_m, floors, inset_m, height_source, %s, now()
                   FROM synthetic_buildings_stage""",
                (manifest["generator_version"],),
            )
            loaded = connection.execute(
                "SELECT count(*) FROM buildings.synthetic_residential"
            ).fetchone()[0]
            if loaded != expected:
                raise RuntimeError(f"Loaded {loaded} models; expected {expected}")
    finally:
        connection.close()
    logger.info("Published %s generated residential models to PostGIS", loaded)
    return loaded
