CREATE TABLE IF NOT EXISTS evidence_refresh_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL UNIQUE,
    system_power TEXT NOT NULL DEFAULT 'ON',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    markets_checked INTEGER NOT NULL DEFAULT 0,
    orderbook_snapshots_created INTEGER NOT NULL DEFAULT 0,
    orderbook_failures INTEGER NOT NULL DEFAULT 0,
    signals_checked INTEGER NOT NULL DEFAULT 0,
    bindings_created INTEGER NOT NULL DEFAULT 0,
    bindings_refreshed INTEGER NOT NULL DEFAULT 0,
    bindings_rejected INTEGER NOT NULL DEFAULT 0,
    sides_recovered INTEGER NOT NULL DEFAULT 0,
    missing_side_count INTEGER NOT NULL DEFAULT 0,
    fresh_orderbook_blockers_before INTEGER NOT NULL DEFAULT 0,
    fresh_orderbook_blockers_after INTEGER NOT NULL DEFAULT 0,
    binding_blockers_before INTEGER NOT NULL DEFAULT 0,
    binding_blockers_after INTEGER NOT NULL DEFAULT 0,
    missing_side_before INTEGER NOT NULL DEFAULT 0,
    missing_side_after INTEGER NOT NULL DEFAULT 0,
    orders_delta INTEGER NOT NULL DEFAULT 0,
    order_intents_delta INTEGER NOT NULL DEFAULT 0,
    fills_delta INTEGER NOT NULL DEFAULT 0,
    positions_delta INTEGER NOT NULL DEFAULT 0,
    live_actions_delta INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT evidence_refresh_runs_power_check CHECK (system_power IN ('ON', 'OFF')),
    CONSTRAINT evidence_refresh_runs_status_check CHECK (status IN ('OK', 'DEGRADED', 'FAILED', 'BLOCKED', 'SKIPPED'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_refresh_runs_created_at
    ON evidence_refresh_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_refresh_runs_status
    ON evidence_refresh_runs (status);
