"""Read vector snapshots and raster population data from the warehouse."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import box, shape
from src.shared.database import connect_to_warehouse, warehouse_configured

LAYERS = (
    "hcmc_boundary",
    "hcmc_regions",
    "rainwater",
    "flood_history",
    "flood_satellite",
    "flood_satellite_catalog",
    "flood_risk",
    "land_price",
    "parcels",
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
            "reported_ward",
            "reported_district",
            "current_admin_unit",
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
        "title": "Land price references from the published table",
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
            "ward",
            "region_id",
            "match_confidence",
            "publication_match_mode",
            "match_method",
            "geometry_coverage",
            "city_boundary_clipped",
            "source_values_reviewed",
            "osm_way_ids",
            "geometry_license",
            "source_url",
            "pdf_page",
            "review_note",
        ],
        "time_enabled": False,
        "time_field": None,
    },
    "parcels": {
        "title": "HCMC cadastral land plots",
        "geometry": ["Polygon", "MultiPolygon"],
        "fields": ["uniq_id", "tinh", "quan", "phuong", "to_ban_do", "thua", "mdsdd", "loai_dat_qh", "quyet_dinh", "do_an"],
        "time_enabled": False,
        "time_field": None,
    },
}


LAYER_INFO.update({
    "hcmc_boundary": {"title": "Sourced expanded HCMC analytical boundary", "geometry": ["Polygon", "MultiPolygon"], "fields": ["name"], "time_enabled": False},
    "hcmc_regions": {"title": "Source administrative regions", "geometry": ["Polygon", "MultiPolygon"], "fields": ["name"], "time_enabled": False},
    "rainwater": {"title": "Citywide modeled rainfall", "geometry": ["Polygon", "MultiPolygon"], "fields": ["station_id", "forecast_24h_mm", "forecast_max_3h_mm", "issued_at", "status"], "time_enabled": False},
})

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


def flood_location_context(properties: dict) -> dict:
    """Expose original administrative context without renaming or moving observations."""
    result = dict(properties)
    original = properties.get("original_attributes")
    if isinstance(original, dict):
        for target, source in (
            ("reported_ward", "Ward"),
            ("reported_district", "District_mentioned"),
            ("current_admin_unit", "Current_admin_unit"),
        ):
            if target not in result and original.get(source) is not None:
                result[target] = original[source]
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
            if layer == "parcels":
                row = connection.execute(
                    "SELECT coalesce(sum(feature_count),0), count(*), max(loaded_at) "
                    "FROM parcels.loaded_tile"
                ).fetchone()
                if not row or not row[1]:
                    raise LayerUnavailable(layer)
                return {"feature_count": row[0], "tile_count": row[1], "updated_at": row[2].isoformat() if row[2] else None}
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
        if layer == "parcels":
            clauses = ["geom IS NOT NULL"]
            arguments = []
            if bounds:
                clauses.append("geom && ST_MakeEnvelope(%s,%s,%s,%s,4326) AND ST_Intersects(geom,ST_MakeEnvelope(%s,%s,%s,%s,4326))")
                arguments.extend((*bounds, *bounds))
            arguments.append(limit + 1)
            with connect_to_warehouse() as connection:
                if connection.execute("SELECT 1 FROM parcels.loaded_tile LIMIT 1").fetchone() is None:
                    raise LayerUnavailable(layer)
                rows = connection.execute(
                    "SELECT id, ST_AsGeoJSON(geom), jsonb_strip_nulls(jsonb_build_object("
                    "'uniq_id',uniq_id,'tinh',tinh,'quan',quan,'phuong',phuong,'to_ban_do',to_ban_do,"
                    "'thua',thua,'mdsdd',mdsdd,'loai_dat_qh',loai_dat_qh,'quyet_dinh',quyet_dinh,'do_an',do_an)) "
                    "FROM parcels.plot WHERE " + " AND ".join(clauses) + " ORDER BY id LIMIT %s",
                    arguments,
                ).fetchall()
            matches = [{"type":"Feature", "id":row[0], "geometry":json.loads(row[1]), "properties":row[2]} for row in rows]
            info = metadata(layer)
            return {"type":"FeatureCollection", "features":matches[:limit], "metadata":{**info,"truncated":len(matches)>limit,"returned":min(len(matches),limit)}}
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
    if layer == "flood_history":
        matches = [
            {**feature, "properties": flood_location_context(feature["properties"])}
            for feature in matches
        ]
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
            parcel_tiles = connection.execute("SELECT count(*) FROM parcels.loaded_tile").fetchone()[0]
            population_years = connection.execute(
                "SELECT count(DISTINCT year) FROM population.population_raster"
            ).fetchone()[0]
        return {
            "storage": "postgis",
            "loaded_layers": count + int(parcel_tiles > 0),
            "loaded_parcel_tiles": parcel_tiles,
            "loaded_population_years": population_years,
        }
    count = len(list((directory() / "layers").glob("*.geojson")))
    return {"storage": "snapshots", "loaded_layers": count, "loaded_population_years": 0}


def vector_tile(layer, z, x, y, start=None, end=None) -> bytes:
    """Build one Mapbox vector tile and preserve scalar GeoJSON properties."""
    if layer == "parcels":
        from app.services.parcels import vector_tile as parcel_tile
        return parcel_tile(z, x, y)
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
                    FROM jsonb_each(
                        CASE WHEN f.layer = 'flood_history' THEN
                            jsonb_strip_nulls(jsonb_build_object(
                                'reported_ward', f.properties #> '{original_attributes,Ward}',
                                'reported_district',
                                    f.properties #> '{original_attributes,District_mentioned}',
                                'current_admin_unit',
                                    f.properties #> '{original_attributes,Current_admin_unit}'
                            )) || f.properties
                        ELSE f.properties END
                    ) AS attribute(key, value)
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
    """Display-only interpolation on an exact XYZ grid; raw sampling is unchanged.

    Keep at least two source/output pixels around the tile before warping,
    including neighbouring storage chunks. Clipping to XYZ loses cell centres.
    Warp once onto the reference grid, then pad/crop to its exact 256px extent.
    """
    with connect_to_warehouse() as connection:
        row = connection.execute(
            """
            WITH source_scale AS (
                SELECT 2 * GREATEST(ABS(ST_ScaleX(rast)), ABS(ST_ScaleY(rast))) AS halo
                FROM population.population_raster WHERE year = %s LIMIT 1
            ), tile AS (
                SELECT ST_TileEnvelope(%s, %s, %s) AS geom
            ), native_tile AS (
                SELECT ST_Transform(geom, 4326) AS geom FROM tile
            ), coverage AS (
                SELECT ST_Expand(t.geom, GREATEST(
                    s.halo,
                    (ST_XMax(t.geom) - ST_XMin(t.geom)) / 128,
                    (ST_YMax(t.geom) - ST_YMin(t.geom)) / 128
                )) AS geom
                FROM native_tile AS t CROSS JOIN source_scale AS s
            ), mosaic AS (
                SELECT ST_Union(ST_Clip(r.rast, 1, c.geom, true)) AS rast
                FROM population.population_raster AS r CROSS JOIN coverage AS c
                WHERE r.year = %s
                  AND ST_ConvexHull(r.rast) && c.geom
                  AND ST_Intersects(r.rast, c.geom)
            ), reference AS (
                SELECT ST_AddBand(ST_MakeEmptyRaster(
                           256, 256, ST_XMin(geom), ST_YMax(geom),
                           (ST_XMax(geom) - ST_XMin(geom)) / 256,
                           (ST_YMin(geom) - ST_YMax(geom)) / 256,
                           0, 0, 3857
                       ), '32BF'::text, -9999::double precision,
                       -9999::double precision) AS rast
                FROM tile
            ), warped AS (
                SELECT ST_Transform(m.rast, ref.rast, 'Bilinear', 0.0) AS rast
                FROM mosaic AS m CROSS JOIN reference AS ref
                WHERE m.rast IS NOT NULL
            )
            SELECT ST_DumpValues(
                       ST_MapAlgebra(ref.rast, 1, w.rast, 1, '[rast2.val]'::text,
                                     '32BF'::text, 'FIRST'::text, '[rast2.val]'::text,
                                     NULL::text, -9999::double precision),
                       1,
                       true
                   )
            FROM warped AS w CROSS JOIN reference AS ref
            """,
            (year, z, x, y, year),
        ).fetchone()
    return row[0] if row and row[0] else None
