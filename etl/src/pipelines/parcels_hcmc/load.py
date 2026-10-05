"""Load decoded land-plot polygons into PostGIS, one vector tile at a time."""

import logging
from pathlib import Path

from psycopg import sql

from src.pipelines.parcels_hcmc.config import ParcelsHCMCConfig, config
from src.pipelines.parcels_hcmc.transform import decode_tile
from src.shared.database import connect_to_warehouse

logger = logging.getLogger(__name__)

_INSERT = """
    INSERT INTO {plot_table} (
        uniq_id, tinh, quan, phuong, to_ban_do, thua, mdsdd,
        loai_dat_qh, quyet_dinh, do_an, tile_z, tile_x, tile_y, geom
    )
    VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
    )
"""


def _qualified(schema: str, table: str) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))


def run(download_dir: Path, settings: ParcelsHCMCConfig = config) -> None:
    """Insert plots from tiles that are not yet recorded in ``loaded_tile``."""
    plot_table = _qualified(settings.database_schema, settings.plot_table)
    loaded_table = _qualified(settings.database_schema, settings.loaded_tile_table)
    insert_plot = sql.SQL(_INSERT).format(plot_table=plot_table)
    already_loaded = sql.SQL("SELECT 1 FROM {} WHERE z = %s AND x = %s AND y = %s").format(loaded_table)
    mark_loaded = sql.SQL(
        "INSERT INTO {} (z, x, y, feature_count) VALUES (%s, %s, %s, %s)"
    ).format(loaded_table)

    tiles = sorted(download_dir.glob("*/*/*.pbf"))
    if not tiles:
        raise FileNotFoundError(f"No parcel tiles found under {download_dir}")

    connection = connect_to_warehouse()
    # The tile check must not leave a transaction open. Otherwise each insert
    # is only a savepoint, and closing the connection rolls the load back.
    connection.autocommit = True
    loaded = skipped = 0
    try:
        for path in tiles:
            tile_z = int(path.parent.parent.name)
            tile_x = int(path.parent.name)
            tile_y = int(path.stem)
            with connection.cursor() as cursor:
                cursor.execute(already_loaded, (tile_z, tile_x, tile_y))
                if cursor.fetchone():
                    skipped += 1
                    continue
            plots = decode_tile(path)
            with connection.transaction():
                with connection.cursor() as cursor:
                    if plots:
                        cursor.executemany(
                            insert_plot,
                            [
                                (
                                    plot.uniq_id,
                                    plot.tinh,
                                    plot.quan,
                                    plot.phuong,
                                    plot.to_ban_do,
                                    plot.thua,
                                    plot.mdsdd,
                                    plot.loai_dat_qh,
                                    plot.quyet_dinh,
                                    plot.do_an,
                                    plot.tile_z,
                                    plot.tile_x,
                                    plot.tile_y,
                                    plot.geojson,
                                )
                                for plot in plots
                            ],
                        )
                    cursor.execute(mark_loaded, (tile_z, tile_x, tile_y, len(plots)))
            loaded += 1
            if loaded % 50 == 0:
                logger.info("Loaded %s tiles (%s already present)", loaded, skipped)
    finally:
        connection.close()
    logger.info("Parcel load finished: loaded %s, skipped %s", loaded, skipped)
