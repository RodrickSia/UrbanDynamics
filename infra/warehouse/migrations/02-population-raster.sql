CREATE SCHEMA IF NOT EXISTS population;

CREATE TABLE IF NOT EXISTS population.population_raster (
    year SMALLINT NOT NULL CHECK (year BETWEEN 1900 AND 2200),
    source_file TEXT NOT NULL,
    tile_index INTEGER NOT NULL CHECK (tile_index > 0),
    rast raster NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (year, tile_index)
);

CREATE INDEX IF NOT EXISTS population_raster_year_idx
    ON population.population_raster (year);

CREATE INDEX IF NOT EXISTS population_raster_hull_gist_idx
    ON population.population_raster USING GIST (ST_ConvexHull(rast));
