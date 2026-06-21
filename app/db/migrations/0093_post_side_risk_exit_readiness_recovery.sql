CREATE TABLE IF NOT EXISTS post_side_risk_exit_recovery_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL DEFAULT 'ON',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    candidates_checked INTEGER NOT NULL DEFAULT 0,
    candidates_with_side INTEGER NOT NULL DEFAULT 0,
    thesis_recovered INTEGER NOT NULL DEFAULT 0,
    thesis_still_blocked INTEGER NOT NULL DEFAULT 0,
    risk_checked INTEGER NOT NULL DEFAULT 0,
    risk_approved_before INTEGER NOT NULL DEFAULT 0,
    risk_approved_after INTEGER NOT NULL DEFAULT 0,
    exit_checked INTEGER NOT NULL DEFAULT 0,
    exit_ready_before INTEGER NOT NULL DEFAULT 0,
    exit_ready_after INTEGER NOT NULL DEFAULT 0,
    eligible_before INTEGER NOT NULL DEFAULT 0,
    eligible_after INTEGER NOT NULL DEFAULT 0,
    paper_intents_before INTEGER NOT NULL DEFAULT 0,
    paper_intents_after INTEGER NOT NULL DEFAULT 0,
    candidates_missing_orderbook INTEGER NOT NULL DEFAULT 0,
    candidates_missing_mid_price INTEGER NOT NULL DEFAULT 0,
    candidates_missing_thesis INTEGER NOT NULL DEFAULT 0,
    candidates_missing_context_edge INTEGER NOT NULL DEFAULT 0,
    candidates_missing_exit_policy INTEGER NOT NULL DEFAULT 0,
    paper_positions_delta INTEGER NOT NULL DEFAULT 0,
    live_orders_delta INTEGER NOT NULL DEFAULT 0,
    real_orders_delta INTEGER NOT NULL DEFAULT 0,
    top_risk_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    top_exit_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT post_side_risk_exit_recovery_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_post_side_risk_exit_recovery_cycle
    ON post_side_risk_exit_recovery_runs (cycle_id);

CREATE INDEX IF NOT EXISTS idx_post_side_risk_exit_recovery_created
    ON post_side_risk_exit_recovery_runs (created_at DESC, id DESC);
