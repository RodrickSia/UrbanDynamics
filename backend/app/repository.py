"""Read vector snapshots and raster population data from the warehouse."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import box, shape
from src.shared.database import connect_to_warehouse, warehouse_configured

LAYERS = (
    "flood_history",
    "flood_satellite",
    "flood_satellite_catalog",
    "flood_risk",
    "land_price",
)
POPULATION_PALETTES = {"pseudocolor", "greyscale", "fire"}
LAYER_INFO = {
    "flood_history": {
        "title": "Reported historical flood observations",
        "geometry": ["Point"],
        "fields": [
            "observed_at",
            "location",
            "depth_min_cm",
            "depth_max_cm",
            "cause",
            "year",
            "spatial_precision",
            "geocoding_method",
        ],
        "time_enabled": True,
        "time_field": "observed_at",
    },
    "flood_satellite": {
        "title": "Satellite pixels classified as flooded",
        "geometry": ["Polygon", "MultiPolygon"],
        "fields": ["observed_at", "item_id", "source_url", "mask_mode", "kind"],
        "time_enabled": True,
        "time_field": "observed_at",
    },
    "flood_satellite_catalog": {
        "title": "Satellite acquisition coverage footprints; flood pixels unverified",
        "geometry": ["Polygon", "MultiPolygon"],
        "fields": ["observed_at", "item_id", "kind", "flood_pixels_verified"],
        "time_enabled": True,
        "time_field": "observed_at",
    },
    "flood_risk": {
        "title": "Rainfall threshold indicators around historical flood locations",
        "geometry": ["Polygon", "MultiPolygon"],
        "fields": [
            "status",
            "rain_3h_mm",
            "threshold_p90_3h_mm",
            "wet_windows",
            "radius_m",
            "station_id",
            "forecast_window_start",
            "issued_at",
            "limitations",
        ],
        "time_enabled": True,
        "time_field": "issued_at",
    },
    "land_price": {
        "title": "Reviewed official reference prices joined to reviewed road segments",
        "geometry": ["LineString", "MultiLineString"],
        "fields": [
            "road",
            "start",
            "end",
            "residential_vnd_m2",
            "commercial_vnd_m2",
            "other_nonagricultural_vnd_m2",
            "effective_from",
            "unit",
            "geometry_reviewed",
            "price_kind",
        ],
        "time_enabled": False,
        "time_field": None,
    },
}


class LayerUnavailable(Exception):
    """Raised when a known layer has no published snapshot."""


def directory() -> Path:
    return Path(os.getenv("DATA_DIR", "data")).resolve()


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def freshness(info: dict) -> dict:
    result = dict(info)
    if result.get("expires_at"):
        result["stale"] = datetime.now(UTC) >= instant(result["expires_at"])
    return result


def time_expression(layer: str, alias: str | None = None) -> str:
    observed_at = f"{alias}.observed_at" if alias else "observed_at"
    if layer == "flood_risk":
        properties = f"{alias}.properties" if alias else "properties"
        return f"COALESCE({observed_at}, NULLIF({properties}->>'issued_at', '')::timestamptz)"
    return observed_at


def metadata(layer: str) -> dict:
    if warehouse_configured():
        with connect_to_warehouse() as connection:
            row = connection.execute(
                "SELECT metadata, updated_at FROM public.layer_snapshots WHERE layer=%s",
                (layer,),
            ).fetchone()
        if row is None:
            raise LayerUnavailable(layer)
        info = dict(row[0])
        info["updated_at"] = row[1].isoformat() if row[1] else None
        return freshness(info)

    path = directory() / "layers" / f"{layer}.geojson"
    if not path.exists():
        raise LayerUnavailable(layer)
    document = json.loads(path.read_text(encoding="utf-8"))
    return freshness(document["metadata"])


def features(layer, bounds=None, start=None, end=None, limit=5000):
    if warehouse_configured():
        clauses = ["layer=%s"]
        arguments = [layer]
        if bounds:
            clauses.append("ST_Intersects(geom,ST_MakeEnvelope(%s,%s,%s,%s,4326))")
            arguments.extend(bounds)
        if start:
            clauses.append(f"{time_expression(layer)} >= %s")
            arguments.append(start)
        if end:
            clauses.append(f"{time_expression(layer)} < %s")
            arguments.append(end)
        arguments.append(limit + 1)
        with connect_to_warehouse() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            snapshot = connection.execute(
                "SELECT metadata FROM public.layer_snapshots WHERE layer=%s", (layer,)
            ).fetchone()
            if snapshot is None:
                raise LayerUnavailable(layer)
            info = freshness(snapshot[0])
            rows = connection.execute(
                "SELECT feature_id, ST_AsGeoJSON(geom), properties "
                "FROM public.layer_features WHERE "
                + " AND ".join(clauses)
                + " ORDER BY feature_id LIMIT %s",
                arguments,
            ).fetchall()
        matches = [
            {
                "type": "Feature",
                "id": row[0],
                "geometry": json.loads(row[1]),
                "properties": row[2],
            }
            for row in rows
        ]
    else:
        info = metadata(layer)
        path = directory() / "layers" / f"{layer}.geojson"
        document = json.loads(path.read_text(encoding="utf-8"))
        viewport = box(*bounds) if bounds else None
        matches = []
        for feature in sorted(document["features"], key=lambda item: str(item["id"])):
            if viewport is not None and not shape(feature["geometry"]).intersects(viewport):
                continue
            observed_at = feature["properties"].get("observed_at")
            if (start or end) and (
                observed_at is None
                or start
                and instant(observed_at) < start
                or end
                and instant(observed_at) >= end
            ):
                continue
            matches.append(feature)
            if len(matches) > limit:
                break
    return {
        "type": "FeatureCollection",
        "features": matches[:limit],
        "metadata": {
            **info,
            "truncated": len(matches) > limit,
            "returned": min(len(matches), limit),
        },
    }


def readiness() -> dict:
    if warehouse_configured():
        with connect_to_warehouse() as connection:
            connection.execute("SELECT 1")
            count = connection.execute("SELECT count(*) FROM public.layer_snapshots").fetchone()[0]
            population_years = connection.execute(
                "SELECT count(DISTINCT year) FROM population.population_raster"
            ).fetchone()[0]
        return {
            "storage": "postgis",
            "loaded_layers": count,
            "loaded_population_years": population_years,
        }
    count = len(list((directory() / "layers").glob("*.geojson")))
    return {"storage": "snapshots", "loaded_layers": count, "loaded_population_years": 0}


def vector_tile(layer, z, x, y, start=None, end=None) -> bytes:
    """Build one Mapbox vector tile and preserve scalar GeoJSON properties."""
    clauses = [
        "f.layer = %s",
        "f.geom && ST_Transform(ST_TileEnvelope(%s, %s, %s), 4326)",
    ]
    arguments = [layer, z, x, y]
    if start:
        clauses.append(f"{time_expression(layer, 'f')} >= %s")
        arguments.append(start)
    if end:
        clauses.append(f"{time_expression(layer, 'f')} < %s")
        arguments.append(end)
    sql = (
        """
        SELECT ST_AsMVT(tile_features, 'features', 4096, 'geom')
        FROM (
            SELECT f.feature_id,
                   (SELECT jsonb_object_agg(attribute.key, attribute.value)
                    FROM jsonb_each(f.properties) AS attribute(key, value)
                    WHERE jsonb_typeof(attribute.value) NOT IN ('object', 'array', 'null'))
                       AS properties,
                   ST_AsMVTGeom(
                       ST_Transform(f.geom, 3857),
                       ST_TileEnvelope(%s, %s, %s), 4096, 64, true
                   ) AS geom
            FROM public.layer_features AS f
            WHERE """
        + " AND ".join(clauses)
        + " AND f.geom IS NOT NULL) AS tile_features"
    )
    with connect_to_warehouse() as connection:
        row = connection.execute(sql, (z, x, y, *arguments)).fetchone()
    return bytes(row[0]) if row and row[0] else b""


def population_years() -> list[dict]:
    with connect_to_warehouse() as connection:
        rows = connection.execute(
            """
            SELECT year, count(*) AS tile_count,
                   array_agg(DISTINCT source_file ORDER BY source_file) AS sources,
                   max(loaded_at) AS loaded_at
            FROM population.population_raster
            GROUP BY year ORDER BY year
            """
        ).fetchall()
    return [
        {
            "year": row[0],
            "tile_count": row[1],
            "sources": row[2],
            "loaded_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


def population_value(year: int, longitude: float, latitude: float):
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            SELECT ST_Value(
                       rast, 1,
                       ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), ST_SRID(rast)),
                       true
                   )
            FROM population.population_raster
            WHERE year = %s
              AND ST_ConvexHull(rast) && ST_SetSRID(ST_MakePoint(%s, %s), 4326)
              AND ST_Intersects(rast, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            ORDER BY tile_index LIMIT 1
            """,
            (longitude, latitude, year, longitude, latitude, longitude, latitude),
        ).fetchone()
    return row[0] if row else None


def population_statistics(year: int, bounds: tuple[float, float, float, float]):
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            WITH viewport AS (
                SELECT ST_MakeEnvelope(%s, %s, %s, %s, 4326) AS geom
            ), clipped AS (
                SELECT ST_Clip(r.rast, 1, v.geom, true) AS rast
                FROM population.population_raster AS r CROSS JOIN viewport AS v
                WHERE r.year = %s AND ST_ConvexHull(r.rast) && v.geom
                  AND ST_Intersects(r.rast, v.geom)
            ), summary AS (
                SELECT ST_SummaryStats(ST_Union(rast), 1, true) AS stats
                FROM clipped
            )
            SELECT (stats).count, (stats).sum, (stats).mean,
                   (stats).stddev, (stats).min, (stats).max
            FROM summary
            """,
            (*bounds, year),
        ).fetchone()
    if row is None or row[0] is None:
        return None
    return {
        "pixel_count": row[0],
        "population_sum": row[1],
        "population_mean_per_pixel": row[2],
        "population_stddev_per_pixel": row[3],
        "population_min_per_pixel": row[4],
        "population_max_per_pixel": row[5],
    }


def population_tile(year: int, z: int, x: int, y: int):
    """Return a 256-square array of population samples for one Web Mercator tile."""
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            WITH tile AS (
                SELECT ST_TileEnvelope(%s, %s, %s) AS geom
            ), mosaic AS (
                SELECT ST_Transform(
                           ST_Union(
                               ST_Clip(r.rast, 1, ST_Transform(t.geom, 4326), true)
                           ),
                           3857
                       ) AS rast
                FROM population.population_raster AS r CROSS JOIN tile AS t
                WHERE r.year = %s
                  AND ST_ConvexHull(r.rast) && ST_Transform(t.geom, 4326)
                  AND ST_Intersects(r.rast, ST_Transform(t.geom, 4326))
            ), reference AS (
                SELECT ST_MakeEmptyRaster(
                           256, 256, ST_XMin(geom), ST_YMax(geom),
                           (ST_XMax(geom) - ST_XMin(geom)) / 256,
                           (ST_YMin(geom) - ST_YMax(geom)) / 256,
                           0, 0, 3857
                       ) AS rast
                FROM tile
            )
            SELECT ST_DumpValues(
                       ST_Resample(m.rast, ref.rast, 'NearestNeighbor', 0.125, false),
                       1,
                       true
                   )
            FROM mosaic AS m CROSS JOIN reference AS ref
            WHERE m.rast IS NOT NULL
            """,
            (z, x, y, year),
        ).fetchone()
    return row[0] if row and row[0] else None
