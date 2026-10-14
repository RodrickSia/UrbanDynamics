CREATE SCHEMA IF NOT EXISTS transport;

CREATE TABLE IF NOT EXISTS transport.traffic_observation (
    id BIGSERIAL PRIMARY KEY,
    source_row_id TEXT NOT NULL,
    source_segment_id TEXT NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    period_minutes SMALLINT NOT NULL DEFAULT 30,
    los CHAR(1) NOT NULL CHECK (los IN ('A', 'B', 'C', 'D', 'E', 'F')),
    source_max_velocity DOUBLE PRECISION,
    source_start_node TEXT,
    source_end_node TEXT,
    source_length_m DOUBLE PRECISION,
    street_id TEXT,
    street_name TEXT,
    street_type TEXT,
    start_lon DOUBLE PRECISION NOT NULL,
    start_lat DOUBLE PRECISION NOT NULL,
    end_lon DOUBLE PRECISION NOT NULL,
    end_lat DOUBLE PRECISION NOT NULL,
    sumo_edge_id TEXT,
    match_method TEXT CHECK (match_method IN ('node_pair', 'geometry')),
    match_distance_m DOUBLE PRECISION,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (source_row_id, sumo_edge_id)
);

CREATE INDEX IF NOT EXISTS traffic_observation_edge_time_idx
    ON transport.traffic_observation (sumo_edge_id, observed_at);
CREATE INDEX IF NOT EXISTS traffic_observation_time_idx
    ON transport.traffic_observation (observed_at);
