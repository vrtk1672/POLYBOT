ALTER TABLE paper_intents
    ADD COLUMN IF NOT EXISTS expired_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS intent_lifecycle_reason TEXT,
    ADD COLUMN IF NOT EXISTS last_execution_attempt_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS execution_attempt_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS opportunity_memory_id TEXT,
    ADD COLUMN IF NOT EXISTS evidence_fingerprint TEXT,
    ADD COLUMN IF NOT EXISTS reactivated_from_memory_id TEXT,
    ADD COLUMN IF NOT EXISTS opportunity_revision INTEGER NOT NULL DEFAULT 1;

ALTER TABLE paper_intents DROP CONSTRAINT IF EXISTS paper_intents_intent_status_check;
ALTER TABLE paper_intents ADD CONSTRAINT paper_intents_intent_status_check CHECK (
    intent_status IN (
        'CREATED',
        'READY',
        'EXECUTING',
        'EXECUTED',
        'POSITION_OPENED',
        'CLOSED',
        'BLOCKED',
        'CANCELLED',
        'ERROR',
        'EXPIRED',
        'RESET_ARCHIVED',
        'RESET_CLOSED',
        'EXPIRED_NO_EXECUTION',
        'CANCELLED_STALE_INTENT',
        'CANCELLED_REPLACED_BY_NEW_EVIDENCE',
        'CANCELLED_SESSION_RESET'
    )
);

CREATE TABLE IF NOT EXISTS opportunity_memory (
    id BIGSERIAL PRIMARY KEY,
    opportunity_memory_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    original_candidate_id TEXT,
    original_runtime_decision_id TEXT,
    original_paper_intent_id TEXT,
    latest_runtime_decision_id TEXT,
    latest_paper_intent_id TEXT,
    opportunity_key TEXT NOT NULL,
    evidence_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'WAITING_FOR_NEW_EVIDENCE',
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_decision TEXT,
    last_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_score NUMERIC(18,8),
    last_defense_level INTEGER,
    last_side_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_arbitration_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_exit_state TEXT,
    last_reason TEXT,
    reactivation_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT opportunity_memory_status_check CHECK (
        status IN ('REMEMBERED','WAITING_FOR_NEW_EVIDENCE','REACTIVATED','EXPIRED')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunity_memory_session_key_fingerprint
    ON opportunity_memory (paper_session_id, opportunity_key, evidence_fingerprint);

CREATE INDEX IF NOT EXISTS idx_opportunity_memory_session_status
    ON opportunity_memory (paper_session_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_opportunity_memory_market_side
    ON opportunity_memory (market_id, side, updated_at DESC);

CREATE TABLE IF NOT EXISTS opportunity_reactivation_events (
    id BIGSERIAL PRIMARY KEY,
    reactivation_event_id TEXT NOT NULL UNIQUE,
    opportunity_memory_id TEXT NOT NULL,
    paper_session_id TEXT,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    previous_evidence_fingerprint TEXT,
    new_evidence_fingerprint TEXT NOT NULL,
    runtime_decision_id TEXT,
    paper_intent_id TEXT,
    reason TEXT NOT NULL,
    evidence_delta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_opportunity_reactivation_session_created
    ON opportunity_reactivation_events (paper_session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_intents_memory
    ON paper_intents (opportunity_memory_id);

CREATE INDEX IF NOT EXISTS idx_paper_intents_fingerprint
    ON paper_intents (paper_session_id, market_id, side, evidence_fingerprint);

CREATE INDEX IF NOT EXISTS idx_paper_intents_expired
    ON paper_intents (paper_session_id, intent_status, expired_at DESC);
