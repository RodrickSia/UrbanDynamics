CREATE EXTENSION IF NOT EXISTS postgis;
CREATE TABLE IF NOT EXISTS building_scenario_runs (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL,
    model_version text NOT NULL,
    input_sha256 text NOT NULL,
    site geometry(Polygon, 4326) NOT NULL,
    document jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS building_scenario_site_idx ON building_scenario_runs USING gist(site);
