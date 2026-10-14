"""Load TomTom flow segments and attach the nearest plausible SUMO edge."""

import csv
import logging
from pathlib import Path

from psycopg import sql

from src.pipelines.road_data_tomtom.config import TomTomConfig, config
from src.shared.database import connect_to_warehouse

logger = logging.getLogger(__name__)
STAGING_COLUMNS = (
    "source_feature_id", "fetched_at_utc", "fetched_at_hcmc", "time_period_hcmc",
    "tile_zoom", "tile_x", "tile_y", "road_category", "road_subcategory",
    "current_speed_kmh", "relative_speed", "road_closure",
    "part_of_two_way_road", "openlr", "geometry_wkt",
)


def run(path: str | Path | None = None, settings: TomTomConfig = config) -> dict[str, int]:
    input_path = Path(path) if path else settings.transformed_file
    if not input_path.is_file():
        raise FileNotFoundError(f"Normalized TomTom CSV not found: {input_path}; run transform first")
    target = sql.SQL("{}.{}").format(
        sql.Identifier(settings.database_schema), sql.Identifier(settings.table)
    )
    db = connect_to_warehouse()
    try:
        with db.transaction():
            with db.cursor() as cursor:
                cursor.execute("""
                    CREATE TEMP TABLE tomtom_flow_stage (
                        source_feature_id TEXT, fetched_at_utc TIMESTAMPTZ,
                        fetched_at_hcmc TIMESTAMPTZ, time_period_hcmc TEXT,
                        tile_zoom SMALLINT, tile_x INTEGER, tile_y INTEGER,
                        road_category TEXT, road_subcategory TEXT,
                        current_speed_kmh DOUBLE PRECISION, relative_speed DOUBLE PRECISION,
                        road_closure BOOLEAN, part_of_two_way_road BOOLEAN,
                        openlr TEXT, geometry_wkt TEXT
                    ) ON COMMIT DROP
                """)
                with input_path.open("r", encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    if tuple(reader.fieldnames or ()) != STAGING_COLUMNS:
                        raise ValueError("Normalized TomTom CSV has unexpected columns; rerun transform")
                    with cursor.copy("COPY tomtom_flow_stage FROM STDIN") as copy:
                        for row in reader:
                            values = [row.get(name) or None for name in STAGING_COLUMNS]
                            for name in ("tile_zoom", "tile_x", "tile_y"):
                                i = STAGING_COLUMNS.index(name)
                                values[i] = int(values[i]) if values[i] else None
                            for name in ("current_speed_kmh", "relative_speed"):
                                i = STAGING_COLUMNS.index(name)
                                values[i] = float(values[i]) if values[i] else None
                            for name in ("road_closure", "part_of_two_way_road"):
                                i = STAGING_COLUMNS.index(name)
                                values[i] = str(values[i]).lower() in {"true", "1", "yes"} if values[i] else None
                            copy.write_row(values)

                cursor.execute(sql.SQL("DELETE FROM {}").format(target))
                cursor.execute(sql.SQL("""
                    INSERT INTO {} (
                        source_feature_id, fetched_at_utc, fetched_at_hcmc,
                        time_period_hcmc, tile_zoom, tile_x, tile_y,
                        road_category, road_subcategory, current_speed_kmh,
                        relative_speed, road_closure, part_of_two_way_road,
                        openlr, geom, sumo_edge_id, match_distance_m
                    )
                    SELECT s.source_feature_id, s.fetched_at_utc, s.fetched_at_hcmc,
                           s.time_period_hcmc, s.tile_zoom, s.tile_x, s.tile_y,
                           s.road_category, s.road_subcategory, s.current_speed_kmh,
                           s.relative_speed, s.road_closure, s.part_of_two_way_road,
                           s.openlr, parsed.geom, matched.edge_id, matched.distance_m
                    FROM tomtom_flow_stage s
                    CROSS JOIN LATERAL (
                        SELECT ST_SetSRID(ST_GeomFromText(s.geometry_wkt), 4326) AS geom
                    ) parsed
                    LEFT JOIN LATERAL (
                        SELECT e.edge_id,
                               ST_Distance(e.geom::geography, parsed.geom::geography) AS distance_m
                        FROM transport.sumo_edge e
                        WHERE e.geom && ST_Expand(parsed.geom, 0.001)
                          AND ST_DWithin(e.geom::geography, parsed.geom::geography, 30)
                        ORDER BY ST_Distance(e.geom::geography, parsed.geom::geography), e.edge_id
                        LIMIT 1
                    ) matched ON TRUE
                """).format(target))
                cursor.execute(sql.SQL("""
                    SELECT COUNT(*), COUNT(*) FILTER (WHERE sumo_edge_id IS NOT NULL),
                           COUNT(DISTINCT fetched_at_utc)
                    FROM {}
                """).format(target))
                total, matched, snapshots = cursor.fetchone()
        result = {"total": total, "matched": matched, "unmatched": total - matched,
                  "snapshots": snapshots}
        logger.info("Loaded TomTom road-flow observations: %s", result)
        return result
    finally:
        db.close()
