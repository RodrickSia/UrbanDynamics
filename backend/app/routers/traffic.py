"""Historical time-of-week traffic estimates on the loaded SUMO road network."""

import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response
from psycopg import Error as DatabaseError

from src.shared.database import connect_to_warehouse, warehouse_configured

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])
HCMC = ZoneInfo("Asia/Ho_Chi_Minh")


def _require_warehouse() -> None:
    if not warehouse_configured():
        raise HTTPException(503, "Traffic prediction requires the PostGIS warehouse")


def _target_period(
    value: datetime | None,
    weekday: int | None = None,
    period: time | None = None,
) -> tuple[datetime, int, int]:
    target = value or datetime.now(HCMC)
    if target.tzinfo is None:
        target = target.replace(tzinfo=HCMC)
    else:
        target = target.astimezone(HCMC)
    minute = period.minute if period is not None else (target.minute // 30) * 30
    hour = period.hour if period is not None else target.hour
    if period is not None and (period.minute not in (0, 30) or period.second or period.microsecond):
        raise HTTPException(422, "period must be on a 30-minute boundary (for example 08:00 or 08:30)")
    selected_weekday = weekday if weekday is not None else target.isoweekday()
    target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    slot = hour * 2 + minute // 30
    # PostgreSQL ISODOW is Monday=1 through Sunday=7.
    return target, selected_weekday, slot


def _validate_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    try:
        values = tuple(float(part) for part in bbox.split(","))
        west, south, east, north = values
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError
        return west, south, east, north
    except (ValueError, TypeError):
        raise HTTPException(400, "bbox must be west,south,east,north in WGS84") from None


def _prediction_ctes() -> str:
    return """
        WITH period_rows AS (
            SELECT o.sumo_edge_id AS edge_id,
                   o.observed_at::date AS observed_date,
                   mode() WITHIN GROUP (ORDER BY o.los) AS daily_los,
                   count(*)::integer AS sample_rows
            FROM transport.traffic_observation AS o
            JOIN transport.sumo_edge AS e ON e.edge_id = o.sumo_edge_id
            WHERE extract(isodow FROM o.observed_at)::integer = %s
              AND (extract(hour FROM o.observed_at)::integer * 2
                   + extract(minute FROM o.observed_at)::integer / 30) = %s
            GROUP BY o.sumo_edge_id, o.observed_at::date
        ), edge_summary AS (
            SELECT edge_id,
                   mode() WITHIN GROUP (ORDER BY daily_los) AS predicted_los,
                   count(*)::integer AS sample_dates,
                   sum(sample_rows)::integer AS sample_rows,
                   avg(CASE daily_los
                       WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2
                       WHEN 'D' THEN 3 WHEN 'E' THEN 4 ELSE 5 END) AS mean_los_score
            FROM period_rows
            GROUP BY edge_id
        ), edge_stats AS (
            SELECT s.*,
                   count(*) FILTER (WHERE p.daily_los = s.predicted_los)::integer AS matching_dates,
                   round((s.mean_los_score * 20)::numeric, 1) AS congestion_score,
                   round((count(*) FILTER (WHERE p.daily_los = s.predicted_los)::numeric
                          / s.sample_dates), 3) AS los_mode_share,
                   CASE
                     WHEN s.sample_dates >= 10
                          AND count(*) FILTER (WHERE p.daily_los = s.predicted_los)::double precision
                              / s.sample_dates >= 0.7 THEN 'high'
                     WHEN s.sample_dates >= 5
                          AND count(*) FILTER (WHERE p.daily_los = s.predicted_los)::double precision
                              / s.sample_dates >= 0.5 THEN 'medium'
                     ELSE 'low'
                   END AS confidence
            FROM edge_summary AS s
            JOIN period_rows AS p USING (edge_id)
            GROUP BY s.edge_id, s.predicted_los, s.sample_dates, s.sample_rows, s.mean_los_score
        ), road_type_fallback AS (
            SELECT e.road_type,
                   mode() WITHIN GROUP (ORDER BY s.predicted_los) AS predicted_los,
                   avg(s.mean_los_score) AS mean_los_score
            FROM edge_stats AS s
            JOIN transport.sumo_edge AS e ON e.edge_id = s.edge_id
            GROUP BY e.road_type
        ), network_fallback AS (
            SELECT mode() WITHIN GROUP (ORDER BY predicted_los) AS predicted_los,
                   avg(mean_los_score) AS mean_los_score
            FROM edge_stats
        ), weekday_rows AS (
            SELECT o.sumo_edge_id AS edge_id,
                   o.observed_at::date AS observed_date,
                   mode() WITHIN GROUP (ORDER BY o.los) AS daily_los,
                   count(*)::integer AS sample_rows
            FROM transport.traffic_observation AS o
            JOIN transport.sumo_edge AS e ON e.edge_id = o.sumo_edge_id
            WHERE extract(isodow FROM o.observed_at)::integer = %s
            GROUP BY o.sumo_edge_id, o.observed_at::date
        ), weekday_edge_stats AS (
            SELECT edge_id,
                   mode() WITHIN GROUP (ORDER BY daily_los) AS predicted_los,
                   avg(CASE daily_los
                       WHEN 'A' THEN 0 WHEN 'B' THEN 1 WHEN 'C' THEN 2
                       WHEN 'D' THEN 3 WHEN 'E' THEN 4 ELSE 5 END) AS mean_los_score
            FROM weekday_rows
            GROUP BY edge_id
        ), weekday_road_type_fallback AS (
            SELECT e.road_type,
                   mode() WITHIN GROUP (ORDER BY s.predicted_los) AS predicted_los,
                   avg(s.mean_los_score) AS mean_los_score
            FROM weekday_edge_stats AS s
            JOIN transport.sumo_edge AS e ON e.edge_id = s.edge_id
            GROUP BY e.road_type
        ), weekday_network_fallback AS (
            SELECT mode() WITHIN GROUP (ORDER BY predicted_los) AS predicted_los,
                   avg(mean_los_score) AS mean_los_score
            FROM weekday_edge_stats
        ), edge_predictions AS (
            SELECT e.edge_id,
                   coalesce(direct.predicted_los, nearby.predicted_los,
                            road_type.predicted_los, network.predicted_los,
                            weekday_road_type.predicted_los,
                            weekday_network.predicted_los) AS predicted_los,
                   coalesce(direct.sample_dates, 0)::integer AS sample_dates,
                   coalesce(direct.sample_rows, 0)::integer AS sample_rows,
                   coalesce(
                       direct.congestion_score,
                       round((coalesce(nearby.mean_los_score, road_type.mean_los_score,
                                      network.mean_los_score,
                                      weekday_road_type.mean_los_score,
                                      weekday_network.mean_los_score) * 20)::numeric, 1)
                   ) AS congestion_score,
                   coalesce(direct.los_mode_share, 0)::double precision AS los_mode_share,
                   coalesce(direct.confidence, 'low') AS confidence,
                   CASE
                     WHEN direct.edge_id IS NOT NULL THEN 'observed_edge'
                     WHEN nearby.edge_id IS NOT NULL THEN 'nearby_observed_edge'
                     WHEN road_type.predicted_los IS NOT NULL THEN 'road_type_estimate'
                     WHEN network.predicted_los IS NOT NULL THEN 'network_estimate'
                     WHEN weekday_road_type.predicted_los IS NOT NULL THEN 'weekday_road_type_estimate'
                     ELSE 'weekday_network_estimate'
                   END AS prediction_basis,
                   round(nearby.distance_m::numeric, 1) AS inference_distance_m
            FROM transport.sumo_edge AS e
            LEFT JOIN edge_stats AS direct ON direct.edge_id = e.edge_id
            LEFT JOIN LATERAL (
                SELECT source_stats.edge_id,
                       source_stats.predicted_los,
                       source_stats.mean_los_score,
                       ST_Distance(e.geom::geography, source.geom::geography) AS distance_m
                FROM transport.sumo_edge AS source
                JOIN edge_stats AS source_stats ON source_stats.edge_id = source.edge_id
                WHERE direct.edge_id IS NULL
                  AND source.geom && ST_Expand(e.geom, 0.02)
                  AND ST_DWithin(e.geom::geography, source.geom::geography, 1500)
                ORDER BY (source.road_type = e.road_type) DESC,
                         e.geom <-> source.geom
                LIMIT 1
            ) AS nearby ON TRUE
            LEFT JOIN road_type_fallback AS road_type ON road_type.road_type = e.road_type
            CROSS JOIN network_fallback AS network
            LEFT JOIN weekday_road_type_fallback AS weekday_road_type
              ON weekday_road_type.road_type = e.road_type
            CROSS JOIN weekday_network_fallback AS weekday_network
        )
    """


@router.get("/catalog")
def traffic_catalog():
    """Report availability of the SUMO network and matched historical traffic."""
    _require_warehouse()
    try:
        with connect_to_warehouse() as connection:
            row = connection.execute("""
                SELECT (SELECT count(*) FROM transport.sumo_edge),
                       (SELECT count(*) FROM transport.traffic_observation),
                       (SELECT count(DISTINCT sumo_edge_id)
                          FROM transport.traffic_observation WHERE sumo_edge_id IS NOT NULL),
                       (SELECT min(observed_at) FROM transport.traffic_observation),
                       (SELECT max(observed_at) FROM transport.traffic_observation)
            """).fetchone()
    except DatabaseError:
        raise HTTPException(503, "Traffic tables are unavailable; run the traffic feature ETL") from None
    edges, observations, matched_edges, first_seen, last_seen = row
    available = edges > 0 and observations > 0 and matched_edges > 0
    return {
        "available": available,
        "network_available": edges > 0,
        "network_edges": edges,
        "historical_observations": observations,
        "matched_edges": matched_edges,
        "historical_range": {
            "start": first_seen.isoformat(sep=" ") if first_seen else None,
            "end": last_seen.isoformat(sep=" ") if last_seen else None,
        },
        "timezone": "Asia/Ho_Chi_Minh",
        "method": "modal historical LOS by SUMO edge, weekday, and 30-minute period",
    }


@router.get("/network")
def sumo_network(
    bbox: str | None = None,
    limit: int = Query(5000, ge=1, le=10000),
):
    """Return the loaded HCMC SUMO road graph as GeoJSON; this is not a simulation."""
    _require_warehouse()
    bounds = _validate_bbox(bbox)
    spatial_filter = "TRUE" if bounds is None else "geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)"
    spatial_args = () if bounds is None else bounds
    try:
        with connect_to_warehouse() as connection:
            rows = connection.execute(
                f"""
                SELECT edge_id, name, road_type, lane_count,
                       (SELECT avg(NULLIF((lane.value->>'speed_mps')::double precision, 0)) * 3.6
                        FROM jsonb_array_elements(lanes) AS lane(value)) AS speed_kmh,
                       ST_AsGeoJSON(geom)
                FROM transport.sumo_edge
                WHERE {spatial_filter}
                ORDER BY edge_id
                LIMIT %s
                """,
                (*spatial_args, limit + 1),
            ).fetchall()
    except DatabaseError:
        raise HTTPException(503, "SUMO road network unavailable") from None
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": row[0],
                "geometry": json.loads(row[5]),
                "properties": {
                    "edge_id": row[0], "name": row[1], "road_type": row[2],
                    "lane_count": row[3], "speed_limit_kmh": round(row[4], 1) if row[4] is not None else None,
                },
            }
            for row in rows[:limit]
        ],
        "metadata": {"source": "transport.sumo_edge", "kind": "SUMO road network, not simulation output", "truncated": len(rows) > limit},
    }


@router.get("/network/tiles/{z}/{x}/{y}.pbf")
def sumo_network_tile(z: int, x: int, y: int):
    """Render loaded SUMO edges as a vector tile for the map layer."""
    _require_warehouse()
    if not 0 <= z <= 18 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "Tile coordinates are outside the XYZ matrix")
    try:
        with connect_to_warehouse() as connection:
            tile = connection.execute(
                """
                SELECT ST_AsMVT(tile_rows, 'features', 4096, 'geom')
                FROM (
                    SELECT edge_id, name, road_type, lane_count,
                           (SELECT avg(NULLIF((lane.value->>'speed_mps')::double precision, 0)) * 3.6
                            FROM jsonb_array_elements(lanes) AS lane(value)) AS speed_limit_kmh,
                           ST_AsMVTGeom(ST_Transform(geom,3857), ST_TileEnvelope(%s,%s,%s), 4096, 64, true) AS geom
                    FROM transport.sumo_edge
                    WHERE geom && ST_Transform(ST_TileEnvelope(%s,%s,%s),4326)
                ) AS tile_rows
                """,
                (z, x, y, z, x, y),
            ).fetchone()[0]
    except DatabaseError:
        raise HTTPException(503, "SUMO road network tiles unavailable") from None
    if not tile:
        return Response(status_code=204, headers={"Cache-Control": "public, max-age=3600"})
    return Response(bytes(tile), media_type="application/vnd.mapbox-vector-tile", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/prediction")
def traffic_prediction(
    at: datetime | None = None,
    bbox: str | None = None,
    limit: int = Query(5000, ge=1, le=10000),
    weekday: int | None = Query(None, ge=1, le=7),
    period: time | None = None,
):
    """Return typical historical congestion for the requested HCMC half-hour."""
    _require_warehouse()
    target, isodow, slot = _target_period(at, weekday, period)
    bounds = _validate_bbox(bbox)
    spatial_filter = "TRUE" if bounds is None else "e.geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)"
    spatial_args = () if bounds is None else bounds
    try:
        with connect_to_warehouse() as connection:
            rows = connection.execute(
                _prediction_ctes() + f"""
                SELECT e.edge_id, e.name, e.road_type, ST_AsGeoJSON(e.geom),
                       p.predicted_los, p.sample_dates, p.sample_rows,
                       p.congestion_score, p.los_mode_share, p.confidence,
                       p.prediction_basis, p.inference_distance_m
                FROM edge_predictions AS p
                JOIN transport.sumo_edge AS e ON e.edge_id = p.edge_id
                WHERE {spatial_filter}
                ORDER BY p.sample_dates DESC, e.edge_id
                LIMIT %s
                """,
                (isodow, slot, isodow, *spatial_args, limit + 1),
            ).fetchall()
    except DatabaseError:
        raise HTTPException(503, "Traffic prediction data unavailable") from None

    features = []
    for row in rows[:limit]:
        (edge_id, name, road_type, geometry, los, sample_dates, sample_rows, score,
         mode_share, confidence, prediction_basis, inference_distance) = row
        features.append({
            "type": "Feature",
            "id": edge_id,
            "geometry": json.loads(geometry),
            "properties": {
                "edge_id": edge_id,
                "name": name,
                "road_type": road_type,
                "predicted_los": los,
                "congestion_score": score,
                "sample_dates": sample_dates,
                "sample_rows": sample_rows,
                "los_mode_share": float(mode_share),
                "confidence": confidence,
                "prediction_basis": prediction_basis,
                "inference_distance_m": float(inference_distance) if inference_distance is not None else None,
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "weekday": isodow,
            "period_start": target.strftime("%H:%M"),
            "period_minutes": 30,
            "timezone": "Asia/Ho_Chi_Minh",
            "method": "historical weekday/time-slot LOS mode, spatially inferred onto uncovered network edges",
            "interpretation": "Typical historical conditions, not a live forecast or SUMO vehicle-count simulation.",
            "truncated": len(rows) > limit,
            "returned": len(features),
        },
    }


@router.get("/prediction/tiles/{z}/{x}/{y}.pbf")
def traffic_prediction_tile(
    z: int,
    x: int,
    y: int,
    at: datetime | None = None,
    weekday: int | None = Query(None, ge=1, le=7),
    period: time | None = None,
):
    """Return the same historical estimate as a MapLibre vector tile."""
    _require_warehouse()
    if not 0 <= z <= 18 or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise HTTPException(404, "Tile coordinates are outside the XYZ matrix")
    target, isodow, slot = _target_period(at, weekday, period)
    try:
        with connect_to_warehouse() as connection:
            tile = connection.execute(
                _prediction_ctes() + """
                SELECT ST_AsMVT(tile_rows, 'features', 4096, 'geom')
                FROM (
                    SELECT e.edge_id, e.name, e.road_type, p.predicted_los,
                           p.congestion_score, p.sample_dates, p.sample_rows,
                           p.los_mode_share, p.confidence, p.prediction_basis,
                           p.inference_distance_m,
                           ST_AsMVTGeom(ST_Transform(e.geom, 3857), ST_TileEnvelope(%s,%s,%s), 4096, 64, true) AS geom
                    FROM edge_predictions AS p
                    JOIN transport.sumo_edge AS e ON e.edge_id = p.edge_id
                    WHERE e.geom && ST_Transform(ST_TileEnvelope(%s,%s,%s),4326)
                ) AS tile_rows
                """,
                (isodow, slot, isodow, z, x, y, z, x, y),
            ).fetchone()[0]
    except DatabaseError:
        raise HTTPException(503, "Traffic prediction tiles unavailable") from None
    if not tile:
        return Response(status_code=204, headers={"Cache-Control": "public, max-age=300"})
    etag = f'W/"traffic-{isodow}-{slot}-{z}-{x}-{y}"'
    return Response(
        bytes(tile),
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "public, max-age=300", "ETag": etag},
    )
