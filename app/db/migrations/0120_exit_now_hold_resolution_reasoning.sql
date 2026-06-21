CREATE TABLE IF NOT EXISTS exit_hold_evaluations (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('PAPER_POSITION','PAPER_CANDIDATE','PAPER_INTENT')),
    subject_id TEXT NOT NULL,
    paper_position_id TEXT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    cost_basis NUMERIC NULL,
    quantity NUMERIC NULL,
    entry_price NUMERIC NULL,
    current_exit_price NUMERIC NULL,
    exit_now_value NUMERIC NULL,
    exit_now_pnl NUMERIC NULL,
    hold_to_resolution_value NUMERIC NULL,
    hold_to_resolution_profit_if_win NUMERIC NULL,
    hold_to_resolution_max_loss NUMERIC NULL,
    time_to_resolution_seconds INTEGER NULL,
    liquidity_exit_quality TEXT NOT NULL DEFAULT 'EXIT_LIQUIDITY_UNKNOWN',
    spread NUMERIC NULL,
    spread_risk TEXT NOT NULL DEFAULT 'SPREAD_RISK_UNKNOWN',
    rules_risk TEXT NOT NULL DEFAULT 'RULES_RISK_UNKNOWN',
    risk_of_reversal TEXT NOT NULL DEFAULT 'UNKNOWN',
    decision TEXT NOT NULL CHECK (decision IN ('EXIT_NOW','HOLD_TO_RESOLUTION','PARTIAL_EXIT_REVIEW','HOLD_REVIEW','EMERGENCY_EXIT_REVIEW','WAIT','INSUFFICIENT_DATA')),
    confidence NUMERIC NULL,
    reason TEXT NOT NULL,
    missing_inputs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exit_hold_sources (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES exit_hold_evaluations(evaluation_id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evaluation_id, source_table, source_record_id, source_type)
);

CREATE INDEX IF NOT EXISTS idx_exit_hold_subject_created
    ON exit_hold_evaluations (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_exit_hold_position_created
    ON exit_hold_evaluations (paper_position_id, created_at DESC)
    WHERE paper_position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_exit_hold_decision_created
    ON exit_hold_evaluations (decision, created_at DESC);
