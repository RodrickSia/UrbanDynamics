"""Extract eligible parcels and an observed residential height distribution."""

import csv
import json
import logging
import os
from pathlib import Path

from src.pipelines.model_generation.config import ModelGenerationConfig, config
from src.shared.database import connect_to_warehouse
from src.shared.data_io import data_dir

logger = logging.getLogger(__name__)

_REQUIRED_TABLES = ("parcels.plot", "buildings.gba_lod1")


def _temporary_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.with_suffix(path.suffix + ".part")


def _require_sources(connection) -> None:
    missing = [
        name
        for name in _REQUIRED_TABLES
        if connection.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0] is None
    ]
    if missing:
        raise RuntimeError(
            "Model generation requires migrated parcel and "
            f"GBA LoD1 tables; missing: {', '.join(missing)}. Load those source datasets first."
        )


def _write_land_use_inventory(connection, target: Path) -> None:
    """Persist counts for every source land-use value in the canonical parcel table."""
    temporary = _temporary_path(target)
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(("parcel_count", "mdsdd"))
        cursor = connection.execute(
            """SELECT coalesce(nullif(trim(mdsdd), ''), '<NULL>') AS land_use,
                      count(*) AS parcel_count
               FROM parcels.plot
               GROUP BY 1
               ORDER BY parcel_count DESC, land_use"""
        )
        for land_use, count in cursor:
            writer.writerow((count, land_use))
    os.replace(temporary, target)


def run(settings: ModelGenerationConfig = config) -> tuple[Path, Path]:
    """Write parcel candidates as JSONL and persist the observed height histogram."""
    root = data_dir() / settings.data_dir.name
    candidate_path = root / "candidates.jsonl"
    candidate_part = _temporary_path(candidate_path)
    distribution_path = root / "residential_height_distribution.json"
    distribution_part = _temporary_path(distribution_path)
    inventory_path = root / "parcel_land_use_inventory.tsv"

    with connect_to_warehouse() as connection:
        _require_sources(connection)
        _write_land_use_inventory(connection, inventory_path)

        histogram = connection.execute(
            """SELECT round(b.height_m * 2) / 2.0 AS height_m, count(*) AS samples
               FROM buildings.gba_lod1 AS b
               WHERE b.height_m BETWEEN %s AND %s
                 AND EXISTS (
                   SELECT 1 FROM parcels.plot AS residential
                   WHERE upper(trim(coalesce(residential.mdsdd, ''))) = ANY(%s)
                     AND NOT residential.conflicting_land_use
                     AND residential.geom && b.geom
                     AND ST_Relate(residential.geom, b.geom, '2********')
                 )
               GROUP BY 1
               ORDER BY 1""",
            (
                settings.minimum_observed_height_m,
                settings.maximum_observed_height_m,
                list(settings.residential_codes),
            ),
        ).fetchall()
        if not histogram:
            raise RuntimeError(
                "No usable GBA heights intersect residential parcels. Load the GBA "
                "snapshot and verify its residential parcel coverage before generating models."
            )
        with distribution_part.open("w", encoding="utf-8") as stream:
            json.dump(
                {
                    "source": settings.height_source,
                    "residential_codes": list(settings.residential_codes),
                    "height_samples": [
                        {"height_m": float(height), "count": int(count)}
                        for height, count in histogram
                    ],
                },
                stream,
                allow_nan=False,
            )

        query = """SELECT p.id, trim(p.mdsdd) AS mdsdd, p.area_m2,
                         ST_AsGeoJSON(ST_Force2D(p.geom)) AS geometry
                  FROM parcels.plot AS p
                  WHERE upper(trim(coalesce(p.mdsdd, ''))) = ANY(%s)
                    AND NOT p.conflicting_land_use
                    AND p.area_m2 BETWEEN %s AND %s
                  ORDER BY p.id"""
        total = 0
        with candidate_part.open("w", encoding="utf-8") as stream:
            with connection.cursor(name="model_generation_candidates") as cursor:
                cursor.execute(
                    query,
                    (
                        list(settings.residential_codes),
                        settings.minimum_parcel_area_m2,
                        settings.maximum_parcel_area_m2,
                    ),
                )
                while rows := cursor.fetchmany(1000):
                    for parcel_id, mdsdd, area_m2, geometry in rows:
                        stream.write(
                            json.dumps(
                                {
                                    "parcel_id": int(parcel_id),
                                    "mdsdd": mdsdd,
                                    "area_m2": float(area_m2),
                                    "geometry": json.loads(geometry),
                                },
                                allow_nan=False,
                                separators=(",", ":"),
                            )
                            + "\n"
                        )
                        total += 1
                    if total and total % 100_000 == 0:
                        logger.info("Extracted %s eligible residential parcels", total)

    os.replace(distribution_part, distribution_path)
    os.replace(candidate_part, candidate_path)
    logger.info(
        "Extracted %s eligible parcels using %s observed height bands; complete land-use "
        "inventory: %s",
        total,
        len(histogram),
        inventory_path,
    )
    return candidate_path, distribution_path
