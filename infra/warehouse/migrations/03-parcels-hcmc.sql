CREATE SCHEMA IF NOT EXISTS parcels;

CREATE TABLE IF NOT EXISTS parcels.land_plot (
    id BIGSERIAL PRIMARY KEY,
    uniq_id TEXT,
    tinh TEXT,
    quan TEXT,
    phuong TEXT,
    to_ban_do TEXT,
    thua TEXT,
    mdsdd TEXT,
    loai_dat_qh TEXT,
    quyet_dinh TEXT,
    do_an TEXT,
    tile_z INTEGER NOT NULL,
    tile_x INTEGER NOT NULL,
    tile_y INTEGER NOT NULL,
    geom geometry(Geometry, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS land_plot_geom_gist_idx
    ON parcels.land_plot USING GIST (geom);

CREATE INDEX IF NOT EXISTS land_plot_tile_idx
    ON parcels.land_plot (tile_z, tile_x, tile_y);

CREATE TABLE IF NOT EXISTS parcels.loaded_tile (
    z INTEGER NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    feature_count INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (z, x, y)
);
