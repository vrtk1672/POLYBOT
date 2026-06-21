CREATE TABLE IF NOT EXISTS mesh_dry_runs (
    id BIGSERIAL PRIMARY KEY,
    dry_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('OK', 'DEGRADED', 'ERROR')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ NULL,
    mode TEXT NULL,
    markets_processed INTEGER NOT NULL DEFAULT 0 CHECK (markets_processed >= 0),
    signals_processed INTEGER NOT NULL DEFAULT 0 CHECK (signals_processed >= 0),
    signal_market_links_created INTEGER NOT NULL DEFAULT 0 CHECK (signal_market_links_created >= 0),
    impact_links_created INTEGER NOT NULL DEFAULT 0 CHECK (impact_links_created >= 0),
    brain_outputs_created INTEGER NOT NULL DEFAULT 0 CHECK (brain_outputs_created >= 0),
    coordinator_decisions_created INTEGER NOT NULL DEFAULT 0 CHECK (coordinator_decisions_created >= 0),
    no_trade_explanations_created INTEGER NOT NULL DEFAULT 0 CHECK (no_trade_explanations_created >= 0),
    execution_allowed BOOLEAN NOT NULL DEFAULT false CHECK (execution_allowed = false),
    paper_orders_before INTEGER NULL CHECK (paper_orders_before IS NULL OR paper_orders_before >= 0),
    paper_orders_after INTEGER NULL CHECK (paper_orders_after IS NULL OR paper_orders_after >= 0),
    shadow_orders_before INTEGER NULL CHECK (shadow_orders_before IS NULL OR shadow_orders_before >= 0),
    shadow_orders_after INTEGER NULL CHECK (shadow_orders_after IS NULL OR shadow_orders_after >= 0),
    live_orders_before INTEGER NULL CHECK (live_orders_before IS NULL OR live_orders_before >= 0),
    live_orders_after INTEGER NULL CHECK (live_orders_after IS NULL OR live_orders_after >= 0),
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_dry_runs_no_order_growth CHECK (
        (paper_orders_before IS NULL OR paper_orders_after IS NULL OR paper_orders_after <= paper_orders_before)
        AND (shadow_orders_before IS NULL OR shadow_orders_after IS NULL OR shadow_orders_after <= shadow_orders_before)
        AND (live_orders_before IS NULL OR live_orders_after IS NULL OR live_orders_after <= live_orders_before)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mesh_dry_runs_dry_run_id
    ON mesh_dry_runs (dry_run_id);

CREATE INDEX IF NOT EXISTS idx_mesh_dry_runs_created_at
    ON mesh_dry_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mesh_dry_runs_status
    ON mesh_dry_runs (status, created_at DESC);

CREATE TABLE IF NOT EXISTS mesh_dry_run_items (
    id BIGSERIAL PRIMARY KEY,
    dry_run_id TEXT NOT NULL REFERENCES mesh_dry_runs(dry_run_id) ON DELETE CASCADE,
    market_id TEXT NULL,
    position_id TEXT NULL,
    final_state TEXT NOT NULL,
    primary_reason TEXT NOT NULL CHECK (length(trim(primary_reason)) > 0),
    signal_count INTEGER NOT NULL DEFAULT 0 CHECK (signal_count >= 0),
    impact_link_count INTEGER NOT NULL DEFAULT 0 CHECK (impact_link_count >= 0),
    brain_output_count INTEGER NOT NULL DEFAULT 0 CHECK (brain_output_count >= 0),
    coordinator_decision_id TEXT NULL REFERENCES coordinator_decisions(coordinator_decision_id) ON DELETE SET NULL,
    no_trade_explanation TEXT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mesh_dry_run_items_dry_run
    ON mesh_dry_run_items (dry_run_id);

CREATE INDEX IF NOT EXISTS idx_mesh_dry_run_items_market
    ON mesh_dry_run_items (market_id);

CREATE INDEX IF NOT EXISTS idx_mesh_dry_run_items_final_state
    ON mesh_dry_run_items (final_state);

CREATE INDEX IF NOT EXISTS idx_mesh_dry_run_items_created_at
    ON mesh_dry_run_items (created_at DESC);
