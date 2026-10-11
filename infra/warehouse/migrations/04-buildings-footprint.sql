CREATE SCHEMA IF NOT EXISTS buildings;

CREATE TABLE IF NOT EXISTS buildings.footprint (
    overture_id TEXT PRIMARY KEY,
    source_release TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS buildings_footprint_geom_gist_idx
    ON buildings.footprint USING GIST (geom);

CREATE INDEX IF NOT EXISTS buildings_footprint_class_idx
    ON buildings.footprint ((properties->>'class'));

CREATE TABLE IF NOT EXISTS buildings.snapshot_metadata (
    dataset TEXT PRIMARY KEY,
    source_release TEXT NOT NULL,
    source_url TEXT NOT NULL,
    boundary_source TEXT NOT NULL,
    feature_count BIGINT NOT NULL CHECK (feature_count >= 0),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
