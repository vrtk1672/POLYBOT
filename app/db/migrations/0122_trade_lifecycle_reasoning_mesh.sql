CREATE TABLE IF NOT EXISTS trade_lifecycle_plans (
    id BIGSERIAL PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('FRESH_SEED','PAPER_CANDIDATE','PAPER_INTENT','PAPER_POSITION')),
    subject_id TEXT NOT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    mesh_session_id TEXT NULL,
    strategy_type TEXT NOT NULL CHECK (strategy_type IN (
        'REPRICING_CANDIDATE',
        'HOLD_TO_RESOLUTION_CANDIDATE',
        'EXIT_NOW_REVIEW',
        'HOLD_REVIEW',
        'CAPITAL_EFFICIENCY_PLAY',
        'WATCH_ONLY',
        'NO_TRADE',
        'INSUFFICIENT_DATA',
        'RISK_BLOCKED',
        'EXIT_BLOCKED',
        'CAPITAL_BLOCKED',
        'SAME_MARKET_BLOCKED',
        'UNKNOWN'
    )),
    plan_status TEXT NOT NULL CHECK (plan_status IN ('COMPLETE','PARTIAL','WATCH','NO_TRADE','BLOCKED','INSUFFICIENT_DATA')),
    decision_class TEXT NOT NULL CHECK (decision_class IN (
        'PAPER_CANDIDATE_REVIEW',
        'PAPER_INTENT_READY_CONTEXT',
        'HOLD_REVIEW',
        'EXIT_REVIEW',
        'NO_TRADE',
        'WATCH',
        'BLOCKED',
        'INSUFFICIENT_DATA'
    )),
    economic_thesis TEXT NOT NULL,
    entry_thesis TEXT NOT NULL,
    exit_thesis TEXT NOT NULL,
    hold_to_resolution_thesis TEXT NOT NULL,
    invalidation_rules_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    capital_plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    monitoring_plan_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    liquidity_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    payout_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    exit_hold_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    capital_efficiency_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    same_market_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    coordinator_judgment_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_inputs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trade_lifecycle_plan_sources (
    id BIGSERIAL PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trade_lifecycle_plans(plan_id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id, source_table, source_record_id, source_type)
);

CREATE TABLE IF NOT EXISTS trade_lifecycle_brain_contributions (
    id BIGSERIAL PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trade_lifecycle_plans(plan_id) ON DELETE CASCADE,
    brain_name TEXT NOT NULL,
    stance TEXT NOT NULL,
    contribution_type TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (plan_id, brain_name, contribution_type)
);

CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_subject_created
    ON trade_lifecycle_plans (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_market_created
    ON trade_lifecycle_plans (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_status_created
    ON trade_lifecycle_plans (plan_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_strategy_created
    ON trade_lifecycle_plans (strategy_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_lifecycle_session_created
    ON trade_lifecycle_plans (mesh_session_id, created_at DESC)
    WHERE mesh_session_id IS NOT NULL;
