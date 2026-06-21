ALTER TABLE paper_sessions
    ADD COLUMN IF NOT EXISTS defense_level INTEGER NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS defense_profile_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS max_deployed_pct NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS max_single_trade_pct NUMERIC(8,4),
    ADD COLUMN IF NOT EXISTS session_learning_report_path TEXT;

ALTER TABLE paper_sessions
    DROP CONSTRAINT IF EXISTS paper_sessions_defense_level_range;

ALTER TABLE paper_sessions
    ADD CONSTRAINT paper_sessions_defense_level_range
    CHECK (defense_level BETWEEN 0 AND 100);

CREATE TABLE IF NOT EXISTS paper_defense_events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT,
    old_defense_level INTEGER,
    new_defense_level INTEGER NOT NULL,
    reason TEXT,
    actor TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_defense_events_session_created
    ON paper_defense_events (paper_session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_learning_ledger (
    id BIGSERIAL PRIMARY KEY,
    learning_ledger_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT,
    runtime_decision_id TEXT,
    paper_intent_id TEXT,
    market_id TEXT,
    side TEXT,
    defense_level INTEGER NOT NULL DEFAULT 100,
    strict_verdict TEXT NOT NULL DEFAULT 'UNKNOWN',
    effective_verdict TEXT NOT NULL DEFAULT 'UNKNOWN',
    strict_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    effective_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ignored_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    softened_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    fallback_requirements_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    base_threshold NUMERIC(12,4),
    adjusted_threshold NUMERIC(12,4),
    opportunity_score NUMERIC(12,4),
    exit_plan_type TEXT,
    entry_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    exit_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_learning_ledger_session_created
    ON paper_learning_ledger (paper_session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_learning_ledger_decision
    ON paper_learning_ledger (runtime_decision_id);
