CREATE TABLE IF NOT EXISTS truth_state_policy (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL UNIQUE,
    ttl_seconds INTEGER NULL,
    criticality TEXT NOT NULL CHECK (criticality IN ('CRITICAL','CONTEXT','HISTORICAL')),
    can_authorize_when_fresh BOOLEAN NOT NULL DEFAULT false,
    stale_behavior TEXT NOT NULL CHECK (stale_behavior IN ('REFRESH_REQUIRED','LAST_KNOWN','HISTORICAL_ONLY','UNKNOWN')),
    historical_behavior TEXT NOT NULL CHECK (historical_behavior IN ('HISTORICAL_ONLY','LAST_KNOWN','UNKNOWN')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS truth_state_registry (
    id BIGSERIAL PRIMARY KEY,
    truth_id TEXT NOT NULL UNIQUE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    subject_type TEXT NULL,
    subject_id TEXT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    truth_state TEXT NOT NULL CHECK (truth_state IN (
        'ACTIVE_FRESH',
        'LAST_KNOWN',
        'HISTORICAL_ONLY',
        'EXPIRED',
        'UNKNOWN',
        'REFRESH_REQUIRED'
    )),
    decision_permission TEXT NOT NULL CHECK (decision_permission IN (
        'CAN_AUTHORIZE',
        'CAN_INFORM_ONLY',
        'CAN_TEACH_ONLY',
        'MUST_REFRESH',
        'MUST_BLOCK',
        'UNKNOWN_PERMISSION'
    )),
    created_at_source TIMESTAMPTZ NULL,
    updated_at_source TIMESTAMPTZ NULL,
    last_verified_at TIMESTAMPTZ NULL,
    ttl_seconds INTEGER NULL,
    age_seconds INTEGER NULL,
    freshness_reason TEXT NOT NULL,
    previous_truth_id TEXT NULL,
    superseded_by_truth_id TEXT NULL,
    is_current_for_subject BOOLEAN NOT NULL DEFAULT false,
    is_current_for_market BOOLEAN NOT NULL DEFAULT false,
    is_historical_memory BOOLEAN NOT NULL DEFAULT false,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_table, source_record_id, source_type)
);

CREATE TABLE IF NOT EXISTS truth_state_transitions (
    id BIGSERIAL PRIMARY KEY,
    transition_id TEXT NOT NULL UNIQUE,
    truth_id TEXT NOT NULL REFERENCES truth_state_registry(truth_id) ON DELETE CASCADE,
    previous_state TEXT NULL,
    new_state TEXT NOT NULL,
    previous_permission TEXT NULL,
    new_permission TEXT NOT NULL,
    reason TEXT NOT NULL,
    triggered_by_source_table TEXT NULL,
    triggered_by_source_record_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS truth_state_decision_links (
    id BIGSERIAL PRIMARY KEY,
    truth_id TEXT NOT NULL REFERENCES truth_state_registry(truth_id) ON DELETE CASCADE,
    decision_table TEXT NOT NULL,
    decision_record_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    decision_permission TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (truth_id, decision_table, decision_record_id, decision_type)
);

CREATE INDEX IF NOT EXISTS idx_truth_state_registry_subject_current
    ON truth_state_registry (subject_type, subject_id, source_type, is_current_for_subject, updated_at DESC)
    WHERE subject_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_truth_state_registry_market_current
    ON truth_state_registry (market_id, source_type, is_current_for_market, updated_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_truth_state_registry_state_permission
    ON truth_state_registry (truth_state, decision_permission, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_truth_state_registry_source
    ON truth_state_registry (source_table, source_record_id, source_type);

CREATE INDEX IF NOT EXISTS idx_truth_state_transitions_truth
    ON truth_state_transitions (truth_id, created_at DESC);

INSERT INTO truth_state_policy (
    source_type, ttl_seconds, criticality, can_authorize_when_fresh, stale_behavior, historical_behavior
)
VALUES
    ('MARKET_IDENTITY', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('TOKEN_IDENTITY', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('ORDERBOOK_SNAPSHOT', 180, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('TRUSTED_ORDERBOOK', 180, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('EXECUTABLE_PRICE', 180, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('RISK_DECISION', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('EXIT_PLAN', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('CAPITAL_EVALUATION', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('PAYOUT_ODDS', 600, 'CONTEXT', false, 'LAST_KNOWN', 'HISTORICAL_ONLY'),
    ('EXIT_HOLD', 600, 'CONTEXT', false, 'LAST_KNOWN', 'HISTORICAL_ONLY'),
    ('CAPITAL_EFFICIENCY', 600, 'CONTEXT', false, 'LAST_KNOWN', 'HISTORICAL_ONLY'),
    ('TRADE_LIFECYCLE_PLAN', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('LIFECYCLE_PLAN', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('LIFECYCLE_GOVERNANCE', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('SAME_MARKET_GUARD', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('PAPER_INTENT', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('PAPER_CANDIDATE', 600, 'CRITICAL', true, 'REFRESH_REQUIRED', 'HISTORICAL_ONLY'),
    ('PAPER_POSITION_OPEN', NULL, 'CRITICAL', true, 'UNKNOWN', 'HISTORICAL_ONLY'),
    ('PAPER_POSITION_CLOSED', NULL, 'HISTORICAL', false, 'HISTORICAL_ONLY', 'HISTORICAL_ONLY'),
    ('PAPER_CLOSE', NULL, 'HISTORICAL', false, 'HISTORICAL_ONLY', 'HISTORICAL_ONLY'),
    ('CAPITAL_LOCK', NULL, 'CRITICAL', true, 'UNKNOWN', 'HISTORICAL_ONLY'),
    ('CAPITAL_RELEASE', NULL, 'HISTORICAL', false, 'HISTORICAL_ONLY', 'HISTORICAL_ONLY'),
    ('CAPITAL_ACCOUNT_EVENT', NULL, 'HISTORICAL', false, 'HISTORICAL_ONLY', 'HISTORICAL_ONLY'),
    ('MESH_COORDINATOR', 600, 'CONTEXT', false, 'LAST_KNOWN', 'HISTORICAL_ONLY')
ON CONFLICT (source_type) DO UPDATE SET
    ttl_seconds=EXCLUDED.ttl_seconds,
    criticality=EXCLUDED.criticality,
    can_authorize_when_fresh=EXCLUDED.can_authorize_when_fresh,
    stale_behavior=EXCLUDED.stale_behavior,
    historical_behavior=EXCLUDED.historical_behavior,
    updated_at=now();
