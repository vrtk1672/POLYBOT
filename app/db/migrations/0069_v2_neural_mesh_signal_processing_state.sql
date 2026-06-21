CREATE TABLE IF NOT EXISTS signal_processing_states (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    processing_state TEXT NOT NULL CHECK (
        processing_state IN ('NEW', 'LINKED', 'QUALITY_CHECKED', 'BRAIN_USED', 'COORDINATOR_USED', 'IGNORED', 'STALE', 'REJECTED', 'ERROR')
    ),
    previous_state TEXT NULL CHECK (
        previous_state IS NULL
        OR previous_state IN ('NEW', 'LINKED', 'QUALITY_CHECKED', 'BRAIN_USED', 'COORDINATOR_USED', 'IGNORED', 'STALE', 'REJECTED', 'ERROR')
    ),
    quality_evaluation_id BIGINT NULL REFERENCES signal_quality_evaluations(id) ON DELETE SET NULL,
    quality_score NUMERIC(5,4) NULL CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)),
    quality_status TEXT NULL,
    gate_status TEXT NOT NULL CHECK (
        gate_status IN ('NOT_EVALUATED', 'BLOCKED', 'BRAIN_ELIGIBLE', 'PAPER_BLOCKED', 'PAPER_ELIGIBLE_INFORMATIONAL_ONLY', 'STALE', 'ERROR')
    ),
    gate_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_requirements_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    linked_to_market BOOLEAN NOT NULL DEFAULT false,
    linked_to_position BOOLEAN NOT NULL DEFAULT false,
    used_by_brain_output BOOLEAN NOT NULL DEFAULT false,
    used_by_coordinator BOOLEAN NOT NULL DEFAULT false,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT false,
    is_runtime_generated BOOLEAN NOT NULL DEFAULT false,
    is_stale BOOLEAN NOT NULL DEFAULT false,
    can_feed_brain BOOLEAN NOT NULL DEFAULT false,
    can_feed_paper BOOLEAN NOT NULL DEFAULT false,
    rejection_reason TEXT NULL,
    ignored_reason TEXT NULL,
    error_reason TEXT NULL,
    evaluated_at TIMESTAMPTZ NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT signal_processing_states_signal_unique UNIQUE (signal_id),
    CONSTRAINT signal_processing_ignored_requires_reason CHECK (
        processing_state <> 'IGNORED' OR length(trim(COALESCE(ignored_reason, ''))) > 0
    ),
    CONSTRAINT signal_processing_error_requires_reason CHECK (
        processing_state <> 'ERROR' OR length(trim(COALESCE(error_reason, ''))) > 0
    )
);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_signal_id
    ON signal_processing_states (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_state
    ON signal_processing_states (processing_state);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_gate_status
    ON signal_processing_states (gate_status);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_quality_status
    ON signal_processing_states (quality_status);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_can_feed_brain
    ON signal_processing_states (can_feed_brain);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_can_feed_paper
    ON signal_processing_states (can_feed_paper);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_is_stale
    ON signal_processing_states (is_stale);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_updated_at
    ON signal_processing_states (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_processing_states_evaluated_at
    ON signal_processing_states (evaluated_at DESC);

CREATE TABLE IF NOT EXISTS signal_processing_state_history (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    old_state TEXT NULL,
    new_state TEXT NOT NULL,
    old_gate_status TEXT NULL,
    new_gate_status TEXT NOT NULL,
    reason TEXT NULL,
    actor TEXT NULL,
    correlation_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signal_processing_history_signal_id
    ON signal_processing_state_history (signal_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_processing_history_new_state
    ON signal_processing_state_history (new_state, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_processing_history_gate_status
    ON signal_processing_state_history (new_gate_status, created_at DESC);
