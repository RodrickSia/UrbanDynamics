-- max_velocity is treated as km/h for comparison, while retained unchanged as
-- source_max_velocity. This does not alter the SUMO network's lane speeds.
ALTER TABLE transport.traffic_observation
    ADD COLUMN IF NOT EXISTS sumo_mean_lane_speed_mps DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS sumo_mean_lane_speed_kmh DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS source_vs_sumo_speed_delta_kmh DOUBLE PRECISION;

UPDATE transport.traffic_observation AS observation
SET sumo_mean_lane_speed_mps = lane_speeds.mean_speed_mps,
    sumo_mean_lane_speed_kmh = lane_speeds.mean_speed_mps * 3.6,
    source_vs_sumo_speed_delta_kmh = CASE
        WHEN observation.source_max_velocity IS NULL OR lane_speeds.mean_speed_mps IS NULL THEN NULL
        ELSE observation.source_max_velocity - lane_speeds.mean_speed_mps * 3.6
    END
FROM transport.sumo_edge AS edge
CROSS JOIN LATERAL (
    SELECT AVG((lane->>'speed_mps')::DOUBLE PRECISION) AS mean_speed_mps
    FROM jsonb_array_elements(edge.lanes) AS lane_data(lane)
) AS lane_speeds
WHERE observation.sumo_edge_id = edge.edge_id;

CREATE INDEX IF NOT EXISTS traffic_observation_speed_delta_idx
    ON transport.traffic_observation (source_vs_sumo_speed_delta_kmh)
    WHERE source_vs_sumo_speed_delta_kmh IS NOT NULL;
