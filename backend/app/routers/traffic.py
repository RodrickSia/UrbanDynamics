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


def _prediction_ctes(spatial_filter: str) -> str:
    return f"""
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
              AND {spatial_filter}
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
                   count(*) FILTER (WHERE p.daily_los = s.predicted_los)::integer AS matching_dates
            FROM edge_summary AS s
            JOIN period_rows AS p USING (edge_id)
            GROUP BY s.edge_id, s.predicted_los, s.sample_dates, s.sample_rows, s.mean_los_score
        )
    """


def _confidence_sql() -> str:
    return """
        CASE
          WHEN sample_dates >= 10 AND matching_dates::double precision / sample_dates >= 0.7 THEN 'high'
          WHEN sample_dates >= 5 AND matching_dates::double precision / sample_dates >= 0.5 THEN 'medium'
          ELSE 'low'
        END
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
                _prediction_ctes(spatial_filter) + """
                SELECT e.edge_id, e.name, e.road_type, ST_AsGeoJSON(e.geom),
                       s.predicted_los, s.sample_dates, s.sample_rows,
                       round((s.mean_los_score * 20)::numeric, 1),
                       round((s.matching_dates::numeric / s.sample_dates), 3),
                       """ + _confidence_sql() + """
                FROM edge_stats AS s
                JOIN transport.sumo_edge AS e ON e.edge_id = s.edge_id
                ORDER BY s.sample_dates DESC, e.edge_id
                LIMIT %s
                """,
                (isodow, slot, *spatial_args, limit + 1),
            ).fetchall()
    except DatabaseError:
        raise HTTPException(503, "Traffic prediction data unavailable") from None

    features = []
    for row in rows[:limit]:
        edge_id, name, road_type, geometry, los, sample_dates, sample_rows, score, mode_share, confidence = row
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
            "method": "historical weekday/time-slot LOS mode per matched SUMO edge",
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
                _prediction_ctes("e.geom && ST_Transform(ST_TileEnvelope(%s,%s,%s),4326)") + """
                SELECT ST_AsMVT(tile_rows, 'features', 4096, 'geom')
                FROM (
                    SELECT e.edge_id, e.name, e.road_type, s.predicted_los,
                           round((s.mean_los_score * 20)::numeric, 1) AS congestion_score,
                           s.sample_dates, s.sample_rows,
                           round((s.matching_dates::numeric / s.sample_dates), 3) AS los_mode_share,
                           """ + _confidence_sql() + """ AS confidence,
                           ST_AsMVTGeom(ST_Transform(e.geom, 3857), ST_TileEnvelope(%s,%s,%s), 4096, 64, true) AS geom
                    FROM edge_stats AS s
                    JOIN transport.sumo_edge AS e ON e.edge_id = s.edge_id
                ) AS tile_rows
                """,
                (isodow, slot, z, x, y, z, x, y),
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
