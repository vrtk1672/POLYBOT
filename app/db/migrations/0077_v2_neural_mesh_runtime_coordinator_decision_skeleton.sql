CREATE TABLE IF NOT EXISTS runtime_coordinator_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('OK', 'DEGRADED', 'DRY_RUN', 'ERROR')),
    input_runtime_brain_outputs INTEGER NOT NULL DEFAULT 0 CHECK (input_runtime_brain_outputs >= 0),
    eligible_brain_outputs INTEGER NOT NULL DEFAULT 0 CHECK (eligible_brain_outputs >= 0),
    coordinator_decisions_created INTEGER NOT NULL DEFAULT 0 CHECK (coordinator_decisions_created >= 0),
    coordinator_decisions_updated INTEGER NOT NULL DEFAULT 0 CHECK (coordinator_decisions_updated >= 0),
    dry_run_decisions_touched INTEGER NOT NULL DEFAULT 0 CHECK (dry_run_decisions_touched = 0),
    runtime_coordinator_decisions_before INTEGER NOT NULL DEFAULT 0 CHECK (runtime_coordinator_decisions_before >= 0),
    runtime_coordinator_decisions_after INTEGER NOT NULL DEFAULT 0 CHECK (runtime_coordinator_decisions_after >= 0),
    dry_run_coordinator_decisions INTEGER NOT NULL DEFAULT 0 CHECK (dry_run_coordinator_decisions >= 0),
    runtime_brain_outputs INTEGER NOT NULL DEFAULT 0 CHECK (runtime_brain_outputs >= 0),
    dry_run_brain_outputs INTEGER NOT NULL DEFAULT 0 CHECK (dry_run_brain_outputs >= 0),
    provenance_updated INTEGER NOT NULL DEFAULT 0 CHECK (provenance_updated >= 0),
    producer_health_updated BOOLEAN NOT NULL DEFAULT false,
    mesh_blockers_updated BOOLEAN NOT NULL DEFAULT false,
    paper_ready_before BOOLEAN NOT NULL DEFAULT false,
    paper_ready_after BOOLEAN NOT NULL DEFAULT false,
    orders_created INTEGER NOT NULL DEFAULT 0,
    order_intents_created INTEGER NOT NULL DEFAULT 0,
    fills_created INTEGER NOT NULL DEFAULT 0,
    positions_created INTEGER NOT NULL DEFAULT 0,
    live_actions_created INTEGER NOT NULL DEFAULT 0,
    remaining_blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_coordinator_runs_non_executing_check
        CHECK (
            paper_ready_before = false
            AND paper_ready_after = false
            AND orders_created = 0
            AND order_intents_created = 0
            AND fills_created = 0
            AND positions_created = 0
            AND live_actions_created = 0
            AND dry_run_decisions_touched = 0
        )
);

CREATE INDEX IF NOT EXISTS idx_runtime_coordinator_runs_created_at
    ON runtime_coordinator_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_runtime_coordinator_runs_status
    ON runtime_coordinator_runs (status);

CREATE TABLE IF NOT EXISTS runtime_coordinator_decision_inputs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runtime_coordinator_runs(run_id) ON DELETE CASCADE,
    coordinator_decision_id TEXT NULL REFERENCES coordinator_decisions(coordinator_decision_id) ON DELETE SET NULL,
    brain_output_id TEXT NOT NULL REFERENCES brain_outputs(brain_output_id) ON DELETE CASCADE,
    signal_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    brain_confidence NUMERIC(10, 6) NULL CHECK (brain_confidence IS NULL OR (brain_confidence >= 0 AND brain_confidence <= 1)),
    brain_decision_type TEXT NULL,
    coordinator_decision_type TEXT NOT NULL,
    paper_allowed BOOLEAN NOT NULL DEFAULT false,
    execution_allowed BOOLEAN NOT NULL DEFAULT false,
    order_intent_allowed BOOLEAN NOT NULL DEFAULT false,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_coordinator_inputs_non_executing_check
        CHECK (paper_allowed = false AND execution_allowed = false AND order_intent_allowed = false)
);

CREATE INDEX IF NOT EXISTS idx_runtime_coordinator_inputs_run
    ON runtime_coordinator_decision_inputs (run_id);

CREATE INDEX IF NOT EXISTS idx_runtime_coordinator_inputs_decision
    ON runtime_coordinator_decision_inputs (coordinator_decision_id);

CREATE INDEX IF NOT EXISTS idx_runtime_coordinator_inputs_brain_output
    ON runtime_coordinator_decision_inputs (brain_output_id);

CREATE INDEX IF NOT EXISTS idx_runtime_coordinator_inputs_decision_type
    ON runtime_coordinator_decision_inputs (coordinator_decision_type);
