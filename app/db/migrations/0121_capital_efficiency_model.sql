CREATE TABLE IF NOT EXISTS capital_efficiency_evaluations (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('PAPER_POSITION','PAPER_CANDIDATE','PAPER_INTENT','FRESH_SEED')),
    subject_id TEXT NOT NULL,
    paper_position_id TEXT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    capital_locked NUMERIC NULL,
    time_locked_seconds INTEGER NULL,
    time_to_resolution_seconds INTEGER NULL,
    current_exit_pnl NUMERIC NULL,
    potential_reward NUMERIC NULL,
    risk_amount NUMERIC NULL,
    reward_per_locked_dollar NUMERIC NULL,
    reward_per_hour NUMERIC NULL,
    reward_per_dollar_hour NUMERIC NULL,
    current_return_pct NUMERIC NULL,
    hold_return_pct NUMERIC NULL,
    open_exposure NUMERIC NULL,
    available_balance NUMERIC NULL,
    liquidity_exit_quality TEXT NOT NULL DEFAULT 'EXIT_LIQUIDITY_UNKNOWN',
    rules_risk TEXT NOT NULL DEFAULT 'RULES_RISK_UNKNOWN',
    risk_of_reversal TEXT NOT NULL DEFAULT 'UNKNOWN',
    capital_efficiency_score NUMERIC NULL,
    recommendation TEXT NOT NULL CHECK (recommendation IN ('CAPITAL_SUPPORT','CAPITAL_WATCH','CAPITAL_REDUCE_REVIEW','CAPITAL_RELEASE_REVIEW','CAPITAL_BLOCK','CAPITAL_INSUFFICIENT_DATA')),
    confidence NUMERIC NULL,
    reason TEXT NOT NULL,
    missing_inputs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS capital_efficiency_sources (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES capital_efficiency_evaluations(evaluation_id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evaluation_id, source_table, source_record_id, source_type)
);

CREATE INDEX IF NOT EXISTS idx_capital_efficiency_subject_created
    ON capital_efficiency_evaluations (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_capital_efficiency_position_created
    ON capital_efficiency_evaluations (paper_position_id, created_at DESC)
    WHERE paper_position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_capital_efficiency_recommendation_created
    ON capital_efficiency_evaluations (recommendation, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_capital_efficiency_market_created
    ON capital_efficiency_evaluations (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;
