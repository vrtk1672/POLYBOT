CREATE TABLE IF NOT EXISTS no_trade_log (
    id BIGSERIAL PRIMARY KEY,
    no_trade_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    market_family TEXT,
    side TEXT,
    candidate_engine TEXT,
    source_layer TEXT NOT NULL,
    source_run_id TEXT,
    source_record_id TEXT,
    decision_status TEXT NOT NULL,
    primary_reason TEXT NOT NULL,
    reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    opportunity_score NUMERIC(18,8),
    strategy_route_status TEXT,
    capital_allocation_status TEXT,
    risk_gate_decision TEXT,
    execution_block_reason TEXT,
    exit_block_reason TEXT,
    would_have_entry_price NUMERIC(18,8),
    would_have_size_usd NUMERIC(18,8),
    would_have_max_loss_usd NUMERIC(18,8),
    decision_confidence NUMERIC(18,8) NOT NULL DEFAULT 0,
    data_confidence NUMERIC(18,8) NOT NULL DEFAULT 0,
    insufficient_data BOOLEAN NOT NULL DEFAULT FALSE,
    insufficient_data_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_no_trade_source_dedupe
ON no_trade_log (source_layer, source_run_id, source_record_id, decision_status, primary_reason)
WHERE source_run_id IS NOT NULL OR source_record_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS no_trade_reasons (
    id BIGSERIAL PRIMARY KEY,
    no_trade_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_layer TEXT NOT NULL,
    source_field TEXT,
    penalty NUMERIC(18,8),
    hard_block BOOLEAN NOT NULL DEFAULT FALSE,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS no_trade_post_fact_review (
    id BIGSERIAL PRIMARY KEY,
    review_id TEXT NOT NULL UNIQUE,
    no_trade_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    review_time TIMESTAMPTZ NOT NULL,
    review_horizon_seconds INTEGER NOT NULL DEFAULT 0,
    observed_price_at_decision NUMERIC(18,8),
    observed_price_after NUMERIC(18,8),
    observed_max_favorable_move NUMERIC(18,8),
    observed_max_adverse_move NUMERIC(18,8),
    would_have_roi NUMERIC(18,8),
    would_have_drawdown NUMERIC(18,8),
    would_have_exit_possible BOOLEAN,
    liquidity_after_score NUMERIC(18,8),
    decision_correct BOOLEAN,
    review_status TEXT NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS no_trade_regret_score (
    id BIGSERIAL PRIMARY KEY,
    regret_id TEXT NOT NULL UNIQUE,
    no_trade_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    regret_score NUMERIC(18,8) NOT NULL,
    regret_band TEXT NOT NULL,
    missed_upside_score NUMERIC(18,8) NOT NULL DEFAULT 0,
    avoided_loss_score NUMERIC(18,8) NOT NULL DEFAULT 0,
    avoided_risk_score NUMERIC(18,8) NOT NULL DEFAULT 0,
    liquidity_regret_score NUMERIC(18,8) NOT NULL DEFAULT 0,
    confidence NUMERIC(18,8) NOT NULL DEFAULT 0,
    learning_signal TEXT NOT NULL,
    update_memory BOOLEAN NOT NULL DEFAULT FALSE,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_no_trade_log_market ON no_trade_log (market_id);
CREATE INDEX IF NOT EXISTS idx_no_trade_log_family ON no_trade_log (market_family);
CREATE INDEX IF NOT EXISTS idx_no_trade_log_engine ON no_trade_log (candidate_engine);
CREATE INDEX IF NOT EXISTS idx_no_trade_log_layer ON no_trade_log (source_layer);
CREATE INDEX IF NOT EXISTS idx_no_trade_log_reason ON no_trade_log (primary_reason);
CREATE INDEX IF NOT EXISTS idx_no_trade_log_created ON no_trade_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_no_trade_reasons_reason ON no_trade_reasons (reason, severity);
CREATE INDEX IF NOT EXISTS idx_no_trade_reviews_status ON no_trade_post_fact_review (no_trade_id, review_status);
CREATE INDEX IF NOT EXISTS idx_no_trade_regret_band ON no_trade_regret_score (regret_band, created_at DESC);
