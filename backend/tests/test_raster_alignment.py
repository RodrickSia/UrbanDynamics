"""Raster regression checks. PostGIS cases use only transaction-local test data."""
import math
import os
from contextlib import nullcontext

import pytest

from app import repository


def test_tile_uses_source_halo_and_one_reference_aligned_bilinear_warp(monkeypatch):
    class Connection:
        def execute(self, sql, args):
            self.sql, self.args = sql, args
            return self

        def fetchone(self):
            return ([[25.0] * 256 for _ in range(256)],)

    connection = Connection()
    monkeypatch.setattr(repository, 'connect_to_warehouse', lambda: nullcontext(connection))
    assert len(repository.population_tile(2024, 15, 26096, 15395)) == 256
    assert "ST_Expand" in connection.sql
    assert "'Bilinear'" in connection.sql
    assert "ST_Resample" not in connection.sql
    assert "'FIRST'" in connection.sql  # output extent is exactly the XYZ reference
    assert "ST_ScaleX" in connection.sql  # padding follows source resolution, not screen px


@pytest.mark.skipif(os.getenv('POSTGIS_TESTS') != '1', reason='Requires local test PostGIS')
@pytest.mark.parametrize('zoom', [14, 18])
def test_adjacent_tiles_have_no_empty_edges_and_interpolate_continuously(monkeypatch, zoom):
    import numpy as np
    from src.shared.database import connect_to_warehouse

    # No inserts into the warehouse: route this function's table reference to a
    # TEMP fixture on this one connection, then roll it back even on failure.
    with connect_to_warehouse() as connection:
        try:
            connection.execute('CREATE TEMP TABLE raster_fixture (year int, rast raster)')
            connection.execute("""
                INSERT INTO raster_fixture
                SELECT 2024, tile
                FROM ST_Tile(ST_MapAlgebra(ST_AddBand(
                    ST_MakeEmptyRaster(100,100,106.65,10.85,0.001,-0.001,0,0,4326),
                    '32BF'::text,25::double precision,-9999::double precision
                ),1,'32BF','100 + [rast.x]'),25,25) AS tile
            """)

            class FixtureConnection:
                def execute(self, sql, args):
                    return connection.execute(sql.replace('population.population_raster',
                                                          'raster_fixture'), args)

            monkeypatch.setattr(repository, 'connect_to_warehouse',
                                lambda: nullcontext(FixtureConnection()))
            count = 2**zoom
            x = math.floor((106.7 + 180) / 360 * count)
            y = math.floor((1 - math.asinh(math.tan(math.radians(10.8))) / math.pi) / 2 * count)
            tiles = [np.asarray(repository.population_tile(2024, zoom, tx, ty), dtype=float)
                     for tx, ty in [(x,y), (x+1,y), (x,y+1)]]
            for tile in tiles:
                assert tile.shape == (256, 256)
                assert np.isfinite(tile).all(), 'Artificial nodata seam in continuous source'
            left, right, below = tiles
            # A linear source ramp must remain continuous across both source
            # raster chunk boundaries and neighbouring XYZ output tile edges.
            expected_step = 360 / count / 256 / 0.001
            assert np.allclose(right[:,0] - left[:,-1], expected_step, atol=0.002)
            assert np.allclose(below[0,:], left[-1,:], atol=0.002)
            assert np.any(np.abs(left - np.round(left)) > 0.01), 'Not nearest-neighbour blocks'
        finally:
            connection.rollback()
