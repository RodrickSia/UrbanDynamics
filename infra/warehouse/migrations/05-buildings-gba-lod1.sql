CREATE TABLE IF NOT EXISTS buildings.gba_lod1 (
    gba_id TEXT PRIMARY KEY,
    source TEXT,
    source_id TEXT,
    region TEXT,
    height_m DOUBLE PRECISION,
    height_variance DOUBLE PRECISION,
    source_tile TEXT NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (height_m IS NULL OR height_m >= 0),
    CHECK (height_variance IS NULL OR height_variance >= 0)
);

CREATE INDEX IF NOT EXISTS buildings_gba_lod1_geom_gist_idx
    ON buildings.gba_lod1 USING GIST (geom);
CREATE INDEX IF NOT EXISTS buildings_gba_lod1_height_idx
    ON buildings.gba_lod1 (height_m) WHERE height_m IS NOT NULL;
