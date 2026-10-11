"""Clip candidates to the current HCMC boundary and normalize attributes."""

import json
import logging
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

from src.pipelines.buildings_footprint.config import BuildingsFootprintConfig, config

logger = logging.getLogger(__name__)


def _boundary_wkt(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") == "FeatureCollection":
        geometries = [shape(feature["geometry"]) for feature in document.get("features", [])]
    elif document.get("type") == "Feature":
        geometries = [shape(document["geometry"])]
    else:
        geometries = [shape(document)]
    polygons = [geometry for geometry in geometries if not geometry.is_empty]
    if not polygons:
        raise ValueError(f"HCMC boundary contains no geometry: {path}")
    boundary = unary_union(polygons)
    if not boundary.is_valid:
        boundary = boundary.buffer(0)
    if boundary.is_empty or boundary.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"HCMC boundary must be a valid polygon: {path}")
    return boundary.wkt


def run(
    source: str | Path | None = None,
    settings: BuildingsFootprintConfig = config,
) -> Path:
    """Clip the cached Overture candidates and write normalized GeoParquet."""
    import duckdb

    source_path = Path(source) if source else settings.raw_path
    if not source_path.is_file() or source_path.stat().st_size == 0:
        raise FileNotFoundError(f"Overture candidate Parquet is missing: {source_path}")
    if not settings.boundary_path.is_file():
        raise FileNotFoundError(f"Pinned HCMC boundary is missing: {settings.boundary_path}")

    destination = settings.normalized_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    boundary = _boundary_wkt(settings.boundary_path)
    logger.info("Clipping Overture candidates to the expanded HCMC boundary")

    connection = duckdb.connect(
        config={
            "threads": str(settings.duckdb_threads),
            "memory_limit": settings.duckdb_memory_limit,
        }
    )
    try:
        connection.execute("LOAD spatial")
        connection.execute("SET enable_geoparquet_conversion = true")
        connection.execute(
            "CREATE TEMP TABLE city_boundary AS SELECT ST_GeomFromText(?) AS geom",
            [boundary],
        )
        connection.execute(
            f"""
            COPY (
                WITH city AS (
                    SELECT geom FROM city_boundary
                ), clipped AS (
                    SELECT
                        CAST(candidate.id AS VARCHAR) AS overture_id,
                        ST_CollectionExtract(
                            ST_MakeValid(ST_Intersection(candidate.geometry, city.geom)), 3
                        ) AS geom,
                        candidate.name,
                        candidate.subtype,
                        candidate.building_class,
                        candidate.has_parts,
                        candidate.level,
                        candidate.height,
                        candidate.num_floors,
                        candidate.num_floors_underground,
                        candidate.min_height,
                        candidate.is_underground,
                        candidate.roof_height,
                        candidate.sources
                    FROM read_parquet({_literal(str(source_path))}) AS candidate
                    CROSS JOIN city
                    WHERE candidate.id IS NOT NULL
                      AND ST_Intersects(candidate.geometry, city.geom)
                )
                SELECT
                    overture_id,
                    ST_AsWKB(ST_Multi(geom)) AS geometry_wkb,
                    to_json(struct_pack(
                        name := name,
                        subtype := subtype,
                        class := building_class,
                        has_parts := has_parts,
                        level := level,
                        height := height,
                        num_floors := num_floors,
                        num_floors_underground := num_floors_underground,
                        min_height := min_height,
                        is_underground := is_underground,
                        roof_height := roof_height,
                        sources := sources
                    )) AS properties_json
                FROM clipped
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
            ) TO {_literal(str(temporary))}
            (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("HCMC clipping produced no building footprints")
        count = connection.execute(
            f"SELECT count(*) FROM read_parquet({_literal(str(temporary))})"
        ).fetchone()[0]
        if count == 0:
            raise RuntimeError("No Overture building footprints fall inside HCMC")
        temporary.replace(destination)
    except Exception:
        logger.exception("Overture building-footprint transform failed")
        temporary.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    logger.info("Normalized %s HCMC building footprints to %s", count, destination)
    return destination


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
