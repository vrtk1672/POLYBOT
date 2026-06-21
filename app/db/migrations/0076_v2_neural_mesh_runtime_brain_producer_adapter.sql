CREATE TABLE IF NOT EXISTS runtime_brain_producer_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    input_runtime_signals INTEGER NOT NULL DEFAULT 0,
    eligible_signals INTEGER NOT NULL DEFAULT 0,
    brain_outputs_created INTEGER NOT NULL DEFAULT 0,
    brain_outputs_updated INTEGER NOT NULL DEFAULT 0,
    dry_run_outputs_touched INTEGER NOT NULL DEFAULT 0,
    runtime_brain_outputs_before INTEGER NOT NULL DEFAULT 0,
    runtime_brain_outputs_after INTEGER NOT NULL DEFAULT 0,
    dry_run_brain_outputs INTEGER NOT NULL DEFAULT 0,
    coordinator_runtime_decisions INTEGER NOT NULL DEFAULT 0,
    provenance_updated INTEGER NOT NULL DEFAULT 0,
    producer_health_updated BOOLEAN NOT NULL DEFAULT FALSE,
    mesh_blockers_updated BOOLEAN NOT NULL DEFAULT FALSE,
    paper_ready_before BOOLEAN NOT NULL DEFAULT FALSE,
    paper_ready_after BOOLEAN NOT NULL DEFAULT FALSE,
    orders_created INTEGER NOT NULL DEFAULT 0,
    order_intents_created INTEGER NOT NULL DEFAULT 0,
    fills_created INTEGER NOT NULL DEFAULT 0,
    positions_created INTEGER NOT NULL DEFAULT 0,
    live_actions_created INTEGER NOT NULL DEFAULT 0,
    remaining_blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    error_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_brain_producer_status_check
        CHECK (status IN ('OK', 'DEGRADED', 'DRY_RUN', 'ERROR')),
    CONSTRAINT runtime_brain_producer_no_paper_ready_check
        CHECK (paper_ready_before = FALSE AND paper_ready_after = FALSE),
    CONSTRAINT runtime_brain_producer_no_execution_check
        CHECK (
            orders_created = 0
            AND order_intents_created = 0
            AND fills_created = 0
            AND positions_created = 0
            AND live_actions_created = 0
        ),
    CONSTRAINT runtime_brain_producer_no_dry_run_touch_check
        CHECK (dry_run_outputs_touched = 0)
);

CREATE TABLE IF NOT EXISTS runtime_brain_output_inputs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runtime_brain_producer_runs(run_id) ON DELETE CASCADE,
    brain_output_id TEXT,
    signal_id TEXT NOT NULL,
    signal_quality_score NUMERIC,
    signal_processing_state TEXT,
    lineage_status TEXT,
    link_status TEXT,
    decision_type TEXT NOT NULL,
    paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_brain_output_inputs_non_executing_check
        CHECK (paper_allowed = FALSE AND execution_allowed = FALSE)
);

CREATE INDEX IF NOT EXISTS idx_runtime_brain_producer_runs_created_at
    ON runtime_brain_producer_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_runtime_brain_producer_runs_status
    ON runtime_brain_producer_runs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_runtime_brain_output_inputs_run_id
    ON runtime_brain_output_inputs (run_id);

CREATE INDEX IF NOT EXISTS idx_runtime_brain_output_inputs_signal_id
    ON runtime_brain_output_inputs (signal_id);

CREATE INDEX IF NOT EXISTS idx_runtime_brain_output_inputs_brain_output_id
    ON runtime_brain_output_inputs (brain_output_id);
