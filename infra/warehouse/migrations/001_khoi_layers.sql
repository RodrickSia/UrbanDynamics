CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS layer_snapshots (
    layer text PRIMARY KEY,
    metadata jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS layer_features (
    layer text NOT NULL REFERENCES layer_snapshots(layer),
    feature_id text NOT NULL,
    geom geometry(Geometry, 4326) NOT NULL,
    properties jsonb NOT NULL,
    observed_at timestamptz,
    PRIMARY KEY (layer, feature_id)
);
CREATE INDEX IF NOT EXISTS layer_features_geom_idx ON layer_features USING gist(geom);
CREATE INDEX IF NOT EXISTS layer_features_time_idx ON layer_features(layer, observed_at);
