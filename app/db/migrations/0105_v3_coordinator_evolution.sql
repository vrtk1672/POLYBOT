CREATE TABLE IF NOT EXISTS mesh_coordinator_decisions (
    id BIGSERIAL PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    bundle_id TEXT NOT NULL REFERENCES mesh_coordinator_input_bundles(bundle_id) ON DELETE CASCADE,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    position_id TEXT NULL,
    final_stance TEXT NOT NULL,
    final_action TEXT NOT NULL,
    confidence NUMERIC NOT NULL DEFAULT 0,
    source_brain_count INTEGER NOT NULL DEFAULT 0,
    opinion_count INTEGER NOT NULL DEFAULT 0,
    conflicts_detected BOOLEAN NOT NULL DEFAULT false,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    winning_brains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    losing_brains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    supporting_opinions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    opposing_opinions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_reason TEXT NOT NULL,
    safety_status TEXT NOT NULL DEFAULT 'SAFE_NON_EXECUTING',
    coordinator_ready BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_coordinator_decision_stance_chk CHECK (final_stance IN (
        'STRONG_SUPPORT',
        'SUPPORT',
        'WATCH',
        'NO_TRADE',
        'BLOCK',
        'EXIT_WATCH',
        'EXIT_RECOMMENDED',
        'INSUFFICIENT_DATA'
    )),
    CONSTRAINT mesh_coordinator_decision_action_chk CHECK (final_action IN (
        'OBSERVE',
        'WATCH',
        'NO_TRADE',
        'BLOCK',
        'PAPER_CANDIDATE_REVIEW',
        'EXIT_REVIEW',
        'HOLD_REVIEW',
        'INSUFFICIENT_DATA'
    )),
    CONSTRAINT mesh_coordinator_decision_confidence_chk CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT mesh_coordinator_decision_source_count_chk CHECK (source_brain_count >= 0),
    CONSTRAINT mesh_coordinator_decision_opinion_count_chk CHECK (opinion_count >= 0),
    CONSTRAINT mesh_coordinator_decision_conflict_count_chk CHECK (conflict_count >= 0),
    CONSTRAINT mesh_coordinator_decision_safety_chk CHECK (safety_status IN (
        'SAFE_NON_EXECUTING',
        'BLOCKED_NON_EXECUTING',
        'INSUFFICIENT_DATA',
        'ERROR'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_coordinator_decision_session_bundle
    ON mesh_coordinator_decisions (session_id, bundle_id);

CREATE INDEX IF NOT EXISTS idx_mesh_coordinator_decisions_session
    ON mesh_coordinator_decisions (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mesh_coordinator_decisions_stance
    ON mesh_coordinator_decisions (final_stance, final_action, created_at DESC);

CREATE TABLE IF NOT EXISTS mesh_coordinator_decision_sources (
    id BIGSERIAL PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES mesh_coordinator_decisions(decision_id) ON DELETE CASCADE,
    opinion_id TEXT NOT NULL REFERENCES mesh_brain_opinions(opinion_id) ON DELETE CASCADE,
    brain_name TEXT NOT NULL,
    brain_type TEXT NOT NULL,
    stance TEXT NOT NULL,
    confidence NUMERIC NOT NULL DEFAULT 0,
    influence TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_coordinator_decision_source
    ON mesh_coordinator_decision_sources (decision_id, opinion_id);

CREATE INDEX IF NOT EXISTS idx_mesh_coordinator_decision_sources_decision
    ON mesh_coordinator_decision_sources (decision_id, linked_at DESC);

CREATE TABLE IF NOT EXISTS mesh_conflict_records (
    id BIGSERIAL PRIMARY KEY,
    conflict_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    bundle_id TEXT NOT NULL REFERENCES mesh_coordinator_input_bundles(bundle_id) ON DELETE CASCADE,
    decision_id TEXT NOT NULL REFERENCES mesh_coordinator_decisions(decision_id) ON DELETE CASCADE,
    conflict_type TEXT NOT NULL,
    brain_a TEXT NOT NULL,
    stance_a TEXT NOT NULL,
    brain_b TEXT NOT NULL,
    stance_b TEXT NOT NULL,
    severity NUMERIC NOT NULL DEFAULT 0,
    resolution TEXT NOT NULL,
    winner TEXT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_conflict_records_severity_chk CHECK (severity >= 0 AND severity <= 1)
);

CREATE INDEX IF NOT EXISTS idx_mesh_conflict_records_decision
    ON mesh_conflict_records (decision_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mesh_conflict_records_session
    ON mesh_conflict_records (session_id, created_at DESC);
