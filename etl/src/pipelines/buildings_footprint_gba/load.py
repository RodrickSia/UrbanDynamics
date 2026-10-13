"""Atomically publish clipped GBA LoD1 buildings to PostGIS."""

import hashlib
import json
import logging
from pathlib import Path

import ijson
from shapely.geometry import shape

from src.pipelines.buildings_footprint_gba.config import GBABuildingsConfig, config
from src.shared.database import connect_to_warehouse

logger = logging.getLogger(__name__)


def run(source: str | Path | None = None, settings: GBABuildingsConfig = config) -> int:
    """Replace only the GBA snapshot; failures leave the prior one intact."""
    path = Path(source) if source else settings.normalized_path
    if not path.is_file() or not path.stat().st_size:
        raise FileNotFoundError(f"Normalized GBA GeoJSON is missing: {path}")
    connection = connect_to_warehouse()
    try:
        with connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                ("hcmc-gba-lod1",),
            )
            connection.execute(
                "CREATE TEMP TABLE gba_lod1_stage (feature_id TEXT NOT NULL, gba_id TEXT NOT NULL, source TEXT, source_id TEXT, region TEXT, height_m DOUBLE PRECISION, height_variance DOUBLE PRECISION, geometry_json JSONB NOT NULL) ON COMMIT DROP"
            )
            copied = 0
            with (
                path.open("rb") as input_file,
                connection.cursor().copy(
                    "COPY gba_lod1_stage (feature_id, gba_id, source, source_id, region, height_m, height_variance, geometry_json) FROM STDIN"
                ) as copy,
            ):
                for feature in ijson.items(input_file, "features.item", use_float=True):
                    properties = feature.get("properties") or {}
                    geometry = feature.get("geometry")
                    if not geometry:
                        raise ValueError("GBA feature is missing geometry")
                    height_m = properties.get("height_m")
                    variance = properties.get("height_variance")
                    feature_id = properties.get("feature_id")
                    if not feature_id:
                        geometry_wkb = shape(geometry).wkb
                        feature_id = f"{properties['gba_id']}:{hashlib.sha256(geometry_wkb).hexdigest()}"
                    if height_m is not None and height_m < 0:
                        height_m = None
                    if variance is not None and variance < 0:
                        variance = None
                    copy.write_row(
                        (
                            feature_id,
                            properties["gba_id"],
                            properties.get("source"),
                            properties.get("source_id"),
                            properties.get("region"),
                            height_m,
                            variance,
                            json.dumps(geometry),
                        )
                    )
                    copied += 1
                    if copied % (settings.batch_size * 10) == 0:
                        logger.info("Staged %s GBA buildings", copied)

            if copied == 0:
                raise ValueError(
                    "GBA snapshot must be a non-empty GeoJSON FeatureCollection"
                )

            connection.execute("DELETE FROM buildings.gba_lod1")
            connection.execute(
                """
                INSERT INTO buildings.gba_lod1 (
                    feature_id, gba_id, source, source_id, region, height_m, height_variance,
                    source_tile, geom, loaded_at
                )
                SELECT feature_id, gba_id, source, source_id, region, height_m, height_variance,
                    %s,
                    ST_Multi(ST_CollectionExtract(ST_MakeValid(
                        ST_SetSRID(ST_GeomFromGeoJSON(geometry_json::text), 4326)
                    ), 3)), now()
                FROM gba_lod1_stage
                """,
                (settings.tile,),
            )
            actual = connection.execute(
                "SELECT count(*) FROM buildings.gba_lod1"
            ).fetchone()[0]
            if actual != copied:
                raise RuntimeError(f"Loaded {actual} GBA buildings; expected {copied}")
            connection.execute(
                """
                INSERT INTO buildings.snapshot_metadata
                    (dataset, source_release, source_url, boundary_source, feature_count, loaded_at)
                VALUES ('hcmc_gba_lod1', %s, %s, %s, %s, now())
                ON CONFLICT (dataset) DO UPDATE SET
                    source_release = EXCLUDED.source_release,
                    source_url = EXCLUDED.source_url,
                    boundary_source = EXCLUDED.boundary_source,
                    feature_count = EXCLUDED.feature_count,
                    loaded_at = now()
                """,
                (
                    settings.dataset_release,
                    settings.polygon_url,
                    settings.boundary_source,
                    actual,
                ),
            )
    finally:
        connection.close()
    logger.info("Replaced HCMC GBA LoD1 snapshot with %s buildings", actual)
    return actual
