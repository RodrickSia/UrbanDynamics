"""Run with POSTGIS_TESTS=1 against the isolated migrated test warehouse."""
import os
from contextlib import contextmanager

import pytest
from shapely.geometry import box, mapping

from app.services.area_indicators import sources


@pytest.mark.skipif(os.getenv('POSTGIS_TESTS') != '1', reason='Requires isolated PostGIS test database')
def test_population_weights_boundary_cells_deduplicates_tiles_and_excludes_nodata(monkeypatch):
    from src.shared.database import connect_to_warehouse

    connection = connect_to_warehouse()

    @contextmanager
    def transaction():
        yield connection

    monkeypatch.setattr(sources, 'connect_to_warehouse', transaction)
    monkeypatch.setattr(sources, 'warehouse_configured', lambda: True)
    try:
        # Two 0.001-degree cells; the second is NoData. Duplicate source tiles must not inflate totals.
        for tile in (2147483600, 2147483601):
            connection.execute('''INSERT INTO population.population_raster(year,source_file,tile_index,rast)
                VALUES (2200,'indicator-test',%s,
                  ST_SetValue(ST_AddBand(ST_MakeEmptyRaster(2,1,106.76,10.821,0.001,-0.001,0,0,4326),
                    '32BF'::text,-9999,-9999),1,1,1,100))''', (tile,))
        # AOI covers half the populated cell + all the NoData cell.
        value = sources.population(mapping(box(106.7605,10.820,106.762,10.821)))
        assert value['year'] == 2200
        assert value['value'] == pytest.approx(50, rel=1e-4)
        assert value['files'] == ['indicator-test']
        # Tiny AOI excludes the pixel centre but must still count intersected population.
        tiny = sources.population(mapping(box(106.7609,10.820,106.761,10.821)))
        assert tiny['value'] == pytest.approx(10, rel=1e-4)
    finally:
        connection.rollback()
        connection.close()
