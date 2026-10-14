CREATE TABLE IF NOT EXISTS transport.sumo_congestion_run (
    run_id UUID PRIMARY KEY,
    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    period TIME NOT NULL CHECK (extract(minute FROM period) IN (0, 30)
                                AND extract(second FROM period) = 0),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    metadata JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS sumo_congestion_run_queue_idx
    ON transport.sumo_congestion_run (created_at, run_id)
    WHERE status = 'queued';

CREATE UNIQUE INDEX IF NOT EXISTS sumo_congestion_run_one_active_idx
    ON transport.sumo_congestion_run ((true))
    WHERE status IN ('queued', 'running');
