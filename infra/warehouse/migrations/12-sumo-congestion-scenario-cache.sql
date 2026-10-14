DROP INDEX IF EXISTS transport.sumo_congestion_run_one_active_idx;

CREATE UNIQUE INDEX IF NOT EXISTS sumo_congestion_run_one_active_scenario_idx
    ON transport.sumo_congestion_run (weekday, period)
    WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS transport.sumo_congestion_scenario_cache (
    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    period TIME NOT NULL CHECK (extract(minute FROM period) IN (0, 30)
                                 AND extract(second FROM period) = 0),
    run_id UUID NOT NULL UNIQUE REFERENCES transport.sumo_congestion_run(run_id) ON DELETE CASCADE,
    metadata JSONB NOT NULL,
    result_gzip BYTEA NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (weekday, period)
);
