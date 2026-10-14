"""Bounded source queries. No network requests or synthetic fallback observations."""
import json

from psycopg.rows import dict_row
from src.shared.database import connect_to_warehouse, warehouse_configured


def population(geometry):
    if not warehouse_configured():
        return None
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '10s'")
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""
                WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS geom),
                latest AS (SELECT max(year) AS year FROM population.population_raster),
                cells AS (
                    SELECT DISTINCT ON (ST_AsEWKB(p.geom)) p.geom, p.val, r.year, r.source_file
                    FROM population.population_raster r, latest, a,
                    LATERAL ST_PixelAsPolygons(ST_Clip(r.rast,1,
                        ST_Expand(ST_Envelope(a.geom),GREATEST(
                            abs(ST_ScaleX(r.rast))+abs(ST_SkewX(r.rast)),
                            abs(ST_ScaleY(r.rast))+abs(ST_SkewY(r.rast)))),true),1,true) p
                    WHERE r.year=latest.year AND ST_ConvexHull(r.rast) && a.geom
                      AND p.val >= 0 AND ST_Intersects(p.geom,a.geom)
                    ORDER BY ST_AsEWKB(p.geom),r.tile_index
                ), parts AS (
                    SELECT c.*, ST_Area(ST_Transform(ST_Intersection(c.geom,a.geom),32648)) AS area,
                           ST_Area(ST_Transform(c.geom,32648)) AS cell_area
                    FROM cells c,a
                ) SELECT max(year) AS year, sum(val*area/NULLIF(cell_area,0)) AS value,
                         sum(area) AS covered_m2, array_agg(DISTINCT source_file) AS files
                  FROM parts WHERE area > 0
            """, (json.dumps(geometry),))
            row = cursor.fetchone()
    return dict(row) if row and row['value'] is not None else None


def parcels(geometry):
    if not warehouse_configured():
        return None
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '10s'")
        rows = connection.execute("""
            WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS geom)
            SELECT CASE WHEN p.conflicting_land_use THEN NULL ELSE NULLIF(BTRIM(p.mdsdd),'') END,
                   ST_AsGeoJSON(ST_Intersection(p.geom,a.geom))
            FROM parcels.plot p,a WHERE p.geom && a.geom AND ST_Intersects(p.geom,a.geom)
            LIMIT 20001
        """, (json.dumps(geometry),)).fetchall()
    if len(rows) > 20000:
        raise ValueError('Choose a smaller area: more than 20,000 parcels intersect this selection')
    return [{'code': row[0], 'geometry': json.loads(row[1])} for row in rows]
