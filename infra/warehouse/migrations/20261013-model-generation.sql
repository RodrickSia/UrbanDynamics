CREATE SCHEMA IF NOT EXISTS buildings;

CREATE TABLE IF NOT EXISTS buildings.synthetic_residential (
    parcel_id BIGINT PRIMARY KEY,
    mdsdd TEXT NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    height_m DOUBLE PRECISION NOT NULL CHECK (height_m > 0),
    floors SMALLINT NOT NULL CHECK (floors > 0),
    inset_m DOUBLE PRECISION NOT NULL CHECK (inset_m >= 0),
    height_source TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS synthetic_residential_geom_gist_idx
    ON buildings.synthetic_residential USING GIST (geom);

CREATE INDEX IF NOT EXISTS synthetic_residential_mdsdd_idx
    ON buildings.synthetic_residential (mdsdd);
