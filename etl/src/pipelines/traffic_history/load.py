"""Match normalized traffic rows to SUMO edges and upsert observations."""

import csv
import logging
from pathlib import Path

from psycopg import sql

from src.pipelines.traffic_history.config import TrafficHistoryConfig, config
from src.shared.database import connect_to_warehouse

logger = logging.getLogger(__name__)

STAGING_COLUMNS = (
    "source_row_id", "source_segment_id", "observed_at", "period_minutes",
    "los", "source_max_velocity", "source_start_node", "source_end_node",
    "source_length_m", "street_id", "street_name", "street_type",
    "start_lon", "start_lat", "end_lon", "end_lat",
)


def run(path: str | Path | None = None, settings: TrafficHistoryConfig = config) -> dict[str, int]:
    input_path = Path(path) if path else settings.transformed_file
    if not input_path.is_file():
        raise FileNotFoundError(f"Normalized traffic CSV not found: {input_path}; run transform first")

    schema = sql.Identifier(settings.database_schema)
    target = sql.SQL("{}.{}").format(schema, sql.Identifier(settings.table))
    db = connect_to_warehouse()
    try:
        with db.transaction():
            with db.cursor() as cursor:
                cursor.execute("""
                    CREATE TEMP TABLE traffic_history_stage (
                        source_row_id TEXT, source_segment_id TEXT, observed_at TIMESTAMP,
                        period_minutes SMALLINT, los CHAR(1), source_max_velocity DOUBLE PRECISION,
                        source_start_node TEXT, source_end_node TEXT, source_length_m DOUBLE PRECISION,
                        street_id TEXT, street_name TEXT, street_type TEXT,
                        start_lon DOUBLE PRECISION, start_lat DOUBLE PRECISION,
                        end_lon DOUBLE PRECISION, end_lat DOUBLE PRECISION
                    ) ON COMMIT DROP
                """)
                with input_path.open("r", encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    if tuple(reader.fieldnames or ()) != STAGING_COLUMNS:
                        raise ValueError("Normalized traffic CSV has unexpected columns; rerun transform")
                    with cursor.copy("COPY traffic_history_stage FROM STDIN") as copy:
                        for row in reader:
                            copy.write_row(tuple(row[name] or None for name in STAGING_COLUMNS))

                # This table is the snapshot for the checked-in source CSV. Replace
                # it atomically so a previous unmatched run cannot leave stale rows.
                cursor.execute(sql.SQL("DELETE FROM {}").format(target))
                cursor.execute(sql.SQL("""
                    INSERT INTO {} (
                        source_row_id, source_segment_id, observed_at, period_minutes, los,
                        source_max_velocity, source_start_node, source_end_node,
                        source_length_m, street_id, street_name, street_type,
                        start_lon, start_lat, end_lon, end_lat,
                        sumo_edge_id, match_method, match_distance_m,
                        sumo_mean_lane_speed_mps, sumo_mean_lane_speed_kmh,
                        source_vs_sumo_speed_delta_kmh
                    )
                    SELECT s.source_row_id, s.source_segment_id, s.observed_at, s.period_minutes,
                           s.los, s.source_max_velocity, s.source_start_node, s.source_end_node,
                           s.source_length_m, s.street_id, s.street_name, s.street_type,
                           s.start_lon, s.start_lat, s.end_lon, s.end_lat,
                           matched.edge_id, matched.method, matched.distance_m,
                           lane_speeds.mean_speed_mps, lane_speeds.mean_speed_mps * 3.6,
                           CASE WHEN s.source_max_velocity IS NULL OR lane_speeds.mean_speed_mps IS NULL
                                THEN NULL
                                ELSE s.source_max_velocity - lane_speeds.mean_speed_mps * 3.6 END
                    FROM traffic_history_stage s
                    LEFT JOIN LATERAL (
                        SELECT candidate.edge_id, candidate.method, candidate.distance_m
                        FROM (
                            SELECT e.edge_id, 'node_pair'::TEXT AS method, 0.0::DOUBLE PRECISION AS distance_m,
                                   CASE WHEN e.from_node = s.source_start_node THEN 0 ELSE 1 END AS rank,
                                   0.0::DOUBLE PRECISION AS direction_cost
                            FROM transport.sumo_edge e
                            WHERE (e.from_node = s.source_start_node AND e.to_node = s.source_end_node)
                               OR (e.from_node = s.source_end_node AND e.to_node = s.source_start_node)
                            UNION ALL
                            SELECT e.edge_id, 'geometry'::TEXT AS method,
                                   ST_Distance(ST_Transform(e.geom, 32648), ST_Transform(
                                       ST_SetSRID(ST_MakeLine(ST_MakePoint(s.start_lon,s.start_lat), ST_MakePoint(s.end_lon,s.end_lat)),4326),32648
                                   )) AS distance_m,
                                   2 AS rank,
                                   ST_Distance(ST_StartPoint(e.geom)::geography, ST_SetSRID(ST_MakePoint(s.start_lon,s.start_lat),4326)::geography)
                                     + ST_Distance(ST_EndPoint(e.geom)::geography, ST_SetSRID(ST_MakePoint(s.end_lon,s.end_lat),4326)::geography)
                                     AS direction_cost
                            FROM transport.sumo_edge e
                            WHERE ST_DWithin(
                                e.geom::geography,
                                ST_SetSRID(ST_MakeLine(ST_MakePoint(s.start_lon,s.start_lat), ST_MakePoint(s.end_lon,s.end_lat)),4326)::geography,
                                40
                            )
                            AND e.geom && ST_Expand(
                                ST_SetSRID(ST_MakeLine(ST_MakePoint(s.start_lon,s.start_lat), ST_MakePoint(s.end_lon,s.end_lat)),4326),
                                0.0005
                            )
                        ) candidate
                        ORDER BY candidate.rank, candidate.direction_cost, candidate.distance_m, candidate.edge_id
                        LIMIT 1
                    ) matched ON TRUE
                    LEFT JOIN transport.sumo_edge matched_edge ON matched_edge.edge_id = matched.edge_id
                    LEFT JOIN LATERAL (
                        SELECT AVG((lane->>'speed_mps')::DOUBLE PRECISION) AS mean_speed_mps
                        FROM jsonb_array_elements(matched_edge.lanes) AS lane_data(lane)
                    ) lane_speeds ON TRUE
                """).format(target))
                cursor.execute(sql.SQL("""
                    SELECT COUNT(*), COUNT(*) FILTER (WHERE sumo_edge_id IS NOT NULL),
                           COUNT(*) FILTER (WHERE match_method = 'node_pair'),
                           COUNT(*) FILTER (WHERE match_method = 'geometry')
                    FROM {}
                """).format(target))
                total, matched, by_nodes, by_geometry = cursor.fetchone()
        result = {"total": total, "matched": matched, "unmatched": total - matched,
                  "matched_by_node_pair": by_nodes, "matched_by_geometry": by_geometry}
        logger.info("Loaded historical traffic observations: %s", result)
        return result
    finally:
        db.close()
