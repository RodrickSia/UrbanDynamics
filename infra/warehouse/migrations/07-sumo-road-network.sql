CREATE SCHEMA IF NOT EXISTS transport;

CREATE TABLE IF NOT EXISTS transport.sumo_edge (
    edge_id TEXT PRIMARY KEY,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    name TEXT,
    road_type TEXT,
    priority INTEGER NOT NULL,
    lane_count INTEGER NOT NULL,
    lanes JSONB NOT NULL DEFAULT '[]'::jsonb,
    geom geometry(LineString, 4326) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sumo_edge_geom_gist_idx
    ON transport.sumo_edge USING GIST (geom);
CREATE INDEX IF NOT EXISTS sumo_edge_nodes_idx
    ON transport.sumo_edge (from_node, to_node);

CREATE TABLE IF NOT EXISTS transport.sumo_junction (
    junction_id TEXT PRIMARY KEY,
    junction_type TEXT,
    incoming_lanes TEXT[] NOT NULL DEFAULT '{}',
    internal_lanes TEXT[] NOT NULL DEFAULT '{}',
    geom geometry(Point, 4326) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sumo_junction_geom_gist_idx
    ON transport.sumo_junction USING GIST (geom);

CREATE TABLE IF NOT EXISTS transport.sumo_connection (
    id BIGSERIAL PRIMARY KEY,
    from_edge TEXT NOT NULL,
    to_edge TEXT NOT NULL,
    from_lane INTEGER NOT NULL,
    to_lane INTEGER NOT NULL,
    via_lane TEXT,
    direction TEXT,
    state TEXT,
    traffic_light TEXT,
    link_index INTEGER,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS sumo_connection_edges_idx
    ON transport.sumo_connection (from_edge, to_edge);
