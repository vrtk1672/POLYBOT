CREATE TABLE IF NOT EXISTS brain_mesh_activation_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL UNIQUE,
    phase1_cycle_id TEXT NULL,
    system_power TEXT NOT NULL DEFAULT 'ON',
    status TEXT NOT NULL,
    evidence_created INTEGER NOT NULL DEFAULT 0,
    brain_outputs_created INTEGER NOT NULL DEFAULT 0,
    coordinator_decisions_created INTEGER NOT NULL DEFAULT 0,
    thesis_profiles_created INTEGER NOT NULL DEFAULT 0,
    thesis_profiles_updated INTEGER NOT NULL DEFAULT 0,
    position_thesis_profiles_created INTEGER NOT NULL DEFAULT 0,
    position_thesis_profiles_updated INTEGER NOT NULL DEFAULT 0,
    blocked_reason TEXT NULL,
    error_message TEXT NULL,
    orders_created INTEGER NOT NULL DEFAULT 0,
    order_intents_created INTEGER NOT NULL DEFAULT 0,
    fills_created INTEGER NOT NULL DEFAULT 0,
    positions_created INTEGER NOT NULL DEFAULT 0,
    live_actions_created INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT brain_mesh_activation_runs_power_check CHECK (system_power IN ('ON', 'OFF')),
    CONSTRAINT brain_mesh_activation_runs_status_check CHECK (status IN ('OK', 'DEGRADED', 'FAILED', 'BLOCKED', 'SKIPPED'))
);

CREATE INDEX IF NOT EXISTS idx_brain_mesh_activation_runs_created_at
    ON brain_mesh_activation_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_brain_mesh_activation_runs_status
    ON brain_mesh_activation_runs (status);
