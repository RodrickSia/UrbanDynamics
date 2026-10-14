CREATE TABLE IF NOT EXISTS transport.tomtom_traffic_observation (
    source_feature_id TEXT PRIMARY KEY,
    fetched_at_utc TIMESTAMPTZ NOT NULL,
    fetched_at_hcmc TIMESTAMPTZ,
    time_period_hcmc TEXT,
    tile_zoom SMALLINT,
    tile_x INTEGER,
    tile_y INTEGER,
    road_category TEXT,
    road_subcategory TEXT,
    current_speed_kmh DOUBLE PRECISION,
    relative_speed DOUBLE PRECISION,
    road_closure BOOLEAN,
    part_of_two_way_road BOOLEAN,
    openlr TEXT,
    geom geometry(Geometry, 4326) NOT NULL,
    sumo_edge_id TEXT REFERENCES transport.sumo_edge(edge_id) ON DELETE SET NULL,
    match_distance_m DOUBLE PRECISION,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tomtom_traffic_observation_time_idx
    ON transport.tomtom_traffic_observation (fetched_at_utc);
CREATE INDEX IF NOT EXISTS tomtom_traffic_observation_edge_time_idx
    ON transport.tomtom_traffic_observation (sumo_edge_id, fetched_at_utc);
CREATE INDEX IF NOT EXISTS tomtom_traffic_observation_geom_idx
    ON transport.tomtom_traffic_observation USING GIST (geom);
