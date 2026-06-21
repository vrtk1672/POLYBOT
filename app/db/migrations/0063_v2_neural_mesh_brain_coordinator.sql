CREATE TABLE IF NOT EXISTS coordinator_decisions (
    id BIGSERIAL PRIMARY KEY,
    coordinator_decision_id TEXT NOT NULL UNIQUE,
    market_id TEXT NULL,
    position_id TEXT NULL,
    final_state TEXT NOT NULL CHECK (
        final_state IN (
            'NO_TRADE',
            'WATCH',
            'REVIEW_REQUIRED',
            'PAPER_CANDIDATE_BLOCKED',
            'EXIT_REVIEW_REQUIRED',
            'RISK_BLOCKED',
            'INSUFFICIENT_DATA',
            'CONFLICT_REVIEW',
            'DATA_DEGRADED'
        )
    ),
    primary_reason TEXT NOT NULL CHECK (length(trim(primary_reason)) > 0),
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    urgency NUMERIC(10, 6) NULL CHECK (urgency IS NULL OR (urgency >= 0 AND urgency <= 1)),
    conflicts_detected BOOLEAN NOT NULL DEFAULT false,
    governor_required BOOLEAN NOT NULL DEFAULT true,
    execution_allowed BOOLEAN NOT NULL DEFAULT false CHECK (execution_allowed = false),
    approved_actions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    blocked_actions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_reviews_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_brain_count INTEGER NOT NULL DEFAULT 0 CHECK (source_brain_count >= 0),
    input_output_count INTEGER NOT NULL DEFAULT 0 CHECK (input_output_count >= 0),
    conflict_count INTEGER NOT NULL DEFAULT 0 CHECK (conflict_count >= 0),
    correlation_id TEXT NULL,
    ttl_seconds INTEGER NULL CHECK (ttl_seconds IS NULL OR ttl_seconds >= 0),
    expires_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL CHECK (length(trim(status)) > 0),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coordinator_decisions_decision_id
    ON coordinator_decisions (coordinator_decision_id);

CREATE INDEX IF NOT EXISTS idx_coordinator_decisions_market
    ON coordinator_decisions (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordinator_decisions_position
    ON coordinator_decisions (position_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordinator_decisions_state
    ON coordinator_decisions (final_state, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordinator_decisions_status
    ON coordinator_decisions (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordinator_decisions_created_desc
    ON coordinator_decisions (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_coordinator_decisions_correlation
    ON coordinator_decisions (correlation_id);

CREATE INDEX IF NOT EXISTS idx_coordinator_decisions_execution_allowed
    ON coordinator_decisions (execution_allowed);

CREATE TABLE IF NOT EXISTS coordinator_decision_inputs (
    id BIGSERIAL PRIMARY KEY,
    coordinator_decision_id TEXT NOT NULL REFERENCES coordinator_decisions(coordinator_decision_id) ON DELETE CASCADE,
    brain_output_id TEXT NOT NULL REFERENCES brain_outputs(brain_output_id) ON DELETE CASCADE,
    brain TEXT NOT NULL,
    input_role TEXT NULL,
    input_recommendation TEXT NULL,
    input_confidence NUMERIC(10, 6) NULL CHECK (input_confidence IS NULL OR (input_confidence >= 0 AND input_confidence <= 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_coordinator_decision_inputs_decision
    ON coordinator_decision_inputs (coordinator_decision_id);

CREATE INDEX IF NOT EXISTS idx_coordinator_decision_inputs_output
    ON coordinator_decision_inputs (brain_output_id);

CREATE INDEX IF NOT EXISTS idx_coordinator_decision_inputs_brain
    ON coordinator_decision_inputs (brain);

CREATE TABLE IF NOT EXISTS coordinator_decision_conflicts (
    id BIGSERIAL PRIMARY KEY,
    coordinator_decision_id TEXT NOT NULL REFERENCES coordinator_decisions(coordinator_decision_id) ON DELETE CASCADE,
    conflict_type TEXT NOT NULL CHECK (length(trim(conflict_type)) > 0),
    conflict_key TEXT NOT NULL CHECK (length(trim(conflict_key)) > 0),
    conflict_reason TEXT NOT NULL CHECK (length(trim(conflict_reason)) > 0),
    conflict_severity NUMERIC(10, 6) NULL CHECK (conflict_severity IS NULL OR (conflict_severity >= 0 AND conflict_severity <= 1)),
    left_brain TEXT NULL,
    right_brain TEXT NULL,
    left_output_id TEXT NULL,
    right_output_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_coordinator_decision_conflicts_decision
    ON coordinator_decision_conflicts (coordinator_decision_id);

CREATE INDEX IF NOT EXISTS idx_coordinator_decision_conflicts_type
    ON coordinator_decision_conflicts (conflict_type);

CREATE INDEX IF NOT EXISTS idx_coordinator_decision_conflicts_severity
    ON coordinator_decision_conflicts (conflict_severity DESC NULLS LAST, created_at DESC);
