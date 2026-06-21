CREATE TABLE IF NOT EXISTS same_market_side_arbitrations (
    id BIGSERIAL PRIMARY KEY,
    arbitration_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT,
    market_id TEXT NOT NULL,
    defense_level INTEGER NOT NULL DEFAULT 100,
    yes_decision_id TEXT,
    no_decision_id TEXT,
    yes_score NUMERIC(18,8),
    no_score NUMERIC(18,8),
    yes_arbitration_score NUMERIC(18,8),
    no_arbitration_score NUMERIC(18,8),
    selected_side TEXT,
    rejected_side TEXT,
    margin NUMERIC(18,8),
    required_margin NUMERIC(18,8) NOT NULL DEFAULT 0,
    tie_breaker_used TEXT,
    outcome TEXT NOT NULL,
    conflict_type TEXT NOT NULL DEFAULT 'OPPOSING_ENTER',
    ignored_or_softened_conflict BOOLEAN NOT NULL DEFAULT false,
    strict_verdict TEXT NOT NULL DEFAULT 'BLOCKED',
    effective_verdict TEXT NOT NULL DEFAULT 'UNKNOWN',
    reason TEXT NOT NULL DEFAULT '',
    yes_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    no_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_same_market_side_arbitrations_session
    ON same_market_side_arbitrations(paper_session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_same_market_side_arbitrations_market
    ON same_market_side_arbitrations(market_id, created_at DESC);
