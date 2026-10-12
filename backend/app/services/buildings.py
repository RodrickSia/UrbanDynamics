"""GBA heights with conservatively matched Overture footprint geometry."""

from psycopg.types.json import Jsonb
from shapely import from_wkb, total_bounds
from src.shared.database import connect_to_warehouse

from app.services.building_alignment import Building, Reference, align_buildings

MIN_ZOOM = 14
MAX_NATIVE_ZOOM = 16


def snapshot():
    with connect_to_warehouse() as connection:
        row = connection.execute("""
            SELECT feature_count, loaded_at,
                   EXISTS (SELECT 1 FROM buildings.gba_lod1 WHERE height_m > 0)
            FROM buildings.snapshot_metadata
            WHERE dataset = 'hcmc_gba_lod1'
        """).fetchone()
    if not row or row[0] == 0 or not row[2]:
        return None
    return {"feature_count": row[0], "loaded_at": row[1].isoformat()}


def vector_tile(z: int, x: int, y: int) -> bytes:
    if z < MIN_ZOOM:
        return b""
    # Query whole footprints, including competitors outside the output tile.
    # A 150 m halo exceeds two 50 m match searches plus the MVT tile buffer;
    # clipping before matching would make identity depend on the tile boundary.
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '5s'")
        raw = connection.execute("""
            SELECT feature_id, height_m, ST_AsBinary(ST_Transform(geom, 3857)), source, source_id
            FROM buildings.gba_lod1
            WHERE geom && ST_Transform(ST_Expand(ST_TileEnvelope(%s, %s, %s), 150), 4326)
              AND height_m > 0
        """, (z, x, y)).fetchall()
        if not raw:
            return b""
        buildings = [Building(key, height, from_wkb(bytes(geom)), source, source_id)
                     for key, height, geom, source, source_id in raw]
        bounds = tuple(float(v) for v in total_bounds([b.geometry for b in buildings]))
        references = connection.execute("""
            SELECT overture_id, ST_AsBinary(ST_Transform(geom, 3857)), properties->'sources'
            FROM buildings.footprint
            WHERE geom && ST_Transform(ST_Expand(ST_MakeEnvelope(%s, %s, %s, %s, 3857), 50), 4326)
              AND COALESCE(properties->>'is_underground', 'false') <> 'true'
        """, bounds).fetchall()
        reference_shapes = [Reference(key, from_wkb(bytes(geom)), sources or [])
                            for key, geom, sources in references]
        # Include the full reference/source extent, even for a large footprint
        # crossing the tile. Partial parcel coverage could cause false exclusion.
        bounds = tuple(float(v) for v in total_bounds(
            [b.geometry for b in buildings] + [r.geometry for r in reference_shapes]))
        parcels = connection.execute("""
            SELECT ST_AsBinary(geom_web) FROM parcels.plot
            WHERE geom_web && ST_Expand(ST_MakeEnvelope(%s, %s, %s, %s, 3857), 50)
        """, bounds).fetchall()
        aligned = align_buildings(
            buildings, reference_shapes,
            [from_wkb(bytes(row[0])) for row in parcels],
        )
        features = [{
            'feature_id': b.feature_id, 'height_m': b.height_m,
            'geometry_hex': b.geometry.wkb_hex, 'parcel_fit': b.parcel_fit,
            'parcel_coverage': b.parcel_coverage, 'overture_id': b.overture_id,
            'geometry_source': 'overture' if b.overture_id else 'gba',
            'match_method': b.match_method,
            'geometry_status': b.geometry_status,
        } for b in aligned]
        row = connection.execute("""
            WITH selected AS (
                SELECT f.feature_id, f.height_m, f.parcel_fit, f.parcel_coverage,
                       f.overture_id, f.geometry_source, f.match_method, f.geometry_status,
                       ST_AsMVTGeom(ST_GeomFromWKB(decode(f.geometry_hex, 'hex'), 3857),
                                    ST_TileEnvelope(%s, %s, %s), 4096, 64, true) AS geom
                FROM jsonb_to_recordset(%s) AS f(
                    feature_id text, height_m double precision, geometry_hex text,
                    parcel_fit text, parcel_coverage double precision, overture_id text,
                    geometry_source text, match_method text, geometry_status text)
            ) SELECT ST_AsMVT(selected, 'buildings', 4096, 'geom') FROM selected
              WHERE geom IS NOT NULL
        """, (z, x, y, Jsonb(features))).fetchone()
    return bytes(row[0]) if row and row[0] else b""
