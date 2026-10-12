"""Map tiles backed by the GBA LoD1 building snapshot from the ETL."""

from src.shared.database import connect_to_warehouse

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
    # Native tiles stop at z16; MapLibre overzooms them for closer views.
    with connect_to_warehouse() as connection:
        connection.execute("SET LOCAL statement_timeout = '5s'")
        row = connection.execute("""
            WITH bounds AS (
                SELECT ST_TileEnvelope(%s, %s, %s) AS web
            ), selected AS (
                SELECT b.feature_id, b.height_m,
                       ST_AsMVTGeom(ST_Transform(b.geom, 3857), bounds.web,
                                    4096, 64, true) AS geom
                FROM buildings.gba_lod1 b, bounds
                WHERE b.geom && ST_Transform(bounds.web, 4326)
                  AND b.height_m > 0
            )
            SELECT ST_AsMVT(selected, 'buildings', 4096, 'geom') FROM selected
            WHERE geom IS NOT NULL
        """, (z, x, y)).fetchone()
    return bytes(row[0]) if row and row[0] else b""
