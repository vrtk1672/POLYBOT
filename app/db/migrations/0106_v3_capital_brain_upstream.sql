CREATE TABLE IF NOT EXISTS capital_brain_evaluations (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    position_id TEXT NULL,
    account_id TEXT NULL,
    available_balance NUMERIC(18, 8) NULL,
    locked_balance NUMERIC(18, 8) NULL,
    current_balance NUMERIC(18, 8) NULL,
    open_exposure NUMERIC(18, 8) NULL,
    daily_pnl NUMERIC(18, 8) NULL,
    risk_per_trade_pct NUMERIC(10, 6) NULL,
    max_position_size NUMERIC(18, 8) NULL,
    max_daily_loss_pct NUMERIC(10, 6) NULL,
    max_open_positions INTEGER NULL,
    max_total_open_exposure_pct NUMERIC(10, 6) NULL,
    estimated_required_capital NUMERIC(18, 8) NOT NULL DEFAULT 0,
    estimated_max_loss NUMERIC(18, 8) NOT NULL DEFAULT 0,
    estimated_capital_lock_minutes INTEGER NULL,
    capital_efficiency_score NUMERIC NOT NULL DEFAULT 0,
    exposure_fit_score NUMERIC NOT NULL DEFAULT 0,
    balance_fit_score NUMERIC NOT NULL DEFAULT 0,
    decision TEXT NOT NULL,
    confidence NUMERIC NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    missing_inputs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT capital_brain_decision_chk CHECK (decision IN (
        'CAPITAL_SUPPORT',
        'CAPITAL_WATCH',
        'CAPITAL_BLOCK',
        'CAPITAL_RELEASE_REVIEW',
        'CAPITAL_INSUFFICIENT_DATA'
    )),
    CONSTRAINT capital_brain_confidence_chk CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT capital_brain_efficiency_chk CHECK (capital_efficiency_score >= 0 AND capital_efficiency_score <= 1),
    CONSTRAINT capital_brain_exposure_fit_chk CHECK (exposure_fit_score >= 0 AND exposure_fit_score <= 1),
    CONSTRAINT capital_brain_balance_fit_chk CHECK (balance_fit_score >= 0 AND balance_fit_score <= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_capital_brain_evaluations_session
    ON capital_brain_evaluations (session_id);

CREATE INDEX IF NOT EXISTS idx_capital_brain_evaluations_decision
    ON capital_brain_evaluations (decision, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_capital_brain_evaluations_market
    ON capital_brain_evaluations (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS capital_brain_sources (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES capital_brain_evaluations(evaluation_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    source_domain TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_capital_brain_source
    ON capital_brain_sources (evaluation_id, source_domain, source_table, source_record_id);

CREATE INDEX IF NOT EXISTS idx_capital_brain_sources_session
    ON capital_brain_sources (session_id, linked_at DESC);
