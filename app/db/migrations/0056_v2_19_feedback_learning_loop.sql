CREATE TABLE IF NOT EXISTS trade_reviews (
    id BIGSERIAL PRIMARY KEY,
    review_id TEXT NOT NULL UNIQUE,
    trade_id TEXT,
    order_id TEXT,
    exit_plan_id TEXT,
    exit_intent_id TEXT,
    market_id TEXT NOT NULL,
    market_family TEXT,
    side TEXT,
    engine TEXT,
    strategy_route_id TEXT,
    opportunity_run_id TEXT,
    capital_allocation_id TEXT,
    risk_gate_run_id TEXT,
    entry_price NUMERIC(18,8),
    exit_price NUMERIC(18,8),
    entry_time TIMESTAMPTZ,
    exit_time TIMESTAMPTZ,
    hold_seconds INTEGER,
    realized_pnl_usd NUMERIC(18,8),
    realized_roi NUMERIC(18,8),
    roi_per_hour NUMERIC(18,8),
    max_favorable_excursion NUMERIC(18,8),
    max_adverse_excursion NUMERIC(18,8),
    entry_quality_score NUMERIC(18,8),
    exit_quality_score NUMERIC(18,8),
    slippage_accuracy_score NUMERIC(18,8),
    signal_accuracy_score NUMERIC(18,8),
    engine_result TEXT NOT NULL,
    review_status TEXT NOT NULL,
    insufficient_data BOOLEAN NOT NULL DEFAULT FALSE,
    insufficient_data_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signal_performance (
    id BIGSERIAL PRIMARY KEY,
    signal_perf_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_id TEXT,
    signal_type TEXT NOT NULL,
    market_id TEXT,
    market_family TEXT,
    direction TEXT,
    predicted_strength NUMERIC(18,8),
    observed_move NUMERIC(18,8),
    observed_direction TEXT,
    accuracy_score NUMERIC(18,8) NOT NULL,
    usefulness_score NUMERIC(18,8) NOT NULL,
    false_positive BOOLEAN,
    false_negative BOOLEAN,
    latency_seconds INTEGER,
    confidence NUMERIC(18,8) NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS engine_learning (
    id BIGSERIAL PRIMARY KEY,
    engine_learning_id TEXT NOT NULL UNIQUE,
    engine TEXT NOT NULL,
    market_family TEXT,
    market_id TEXT,
    review_id TEXT,
    no_trade_id TEXT,
    observation_type TEXT NOT NULL,
    result TEXT NOT NULL,
    prior_engine_score NUMERIC(18,8),
    new_engine_score NUMERIC(18,8),
    win_rate_delta NUMERIC(18,8),
    roi_delta NUMERIC(18,8),
    slippage_penalty_delta NUMERIC(18,8),
    adverse_selection_delta NUMERIC(18,8),
    confidence NUMERIC(18,8) NOT NULL,
    learning_signal TEXT NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_learning (
    id BIGSERIAL PRIMARY KEY,
    source_learning_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_name TEXT,
    source_id TEXT,
    market_family TEXT,
    observation_type TEXT NOT NULL,
    result TEXT NOT NULL,
    prior_reliability NUMERIC(18,8),
    new_reliability NUMERIC(18,8),
    usefulness_delta NUMERIC(18,8),
    latency_delta NUMERIC(18,8),
    confidence NUMERIC(18,8) NOT NULL,
    learning_signal TEXT NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS whale_learning (
    id BIGSERIAL PRIMARY KEY,
    whale_learning_id TEXT NOT NULL UNIQUE,
    whale_id TEXT NOT NULL,
    market_family TEXT,
    market_id TEXT,
    observation_type TEXT NOT NULL,
    result TEXT NOT NULL,
    prior_follow_value NUMERIC(18,8),
    new_follow_value NUMERIC(18,8),
    prior_noise_score NUMERIC(18,8),
    new_noise_score NUMERIC(18,8),
    hit_rate_delta NUMERIC(18,8),
    timing_quality_delta NUMERIC(18,8),
    confidence NUMERIC(18,8) NOT NULL,
    learning_signal TEXT NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_learning (
    id BIGSERIAL PRIMARY KEY,
    ai_learning_id TEXT NOT NULL UNIQUE,
    ai_request_id TEXT,
    model_name TEXT,
    prompt_version TEXT,
    market_id TEXT,
    market_family TEXT,
    task_type TEXT NOT NULL,
    predicted_output_json JSONB,
    observed_outcome_json JSONB,
    usefulness_score NUMERIC(18,8) NOT NULL,
    accuracy_score NUMERIC(18,8) NOT NULL,
    cost_usd NUMERIC(18,8),
    cost_efficiency_score NUMERIC(18,8),
    prior_model_score NUMERIC(18,8),
    new_model_score NUMERIC(18,8),
    confidence NUMERIC(18,8) NOT NULL,
    learning_signal TEXT NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS no_trade_learning (
    id BIGSERIAL PRIMARY KEY,
    no_trade_learning_id TEXT NOT NULL UNIQUE,
    no_trade_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_family TEXT,
    candidate_engine TEXT,
    regret_band TEXT NOT NULL,
    regret_score NUMERIC(18,8),
    learning_signal TEXT NOT NULL,
    suggested_filter_change TEXT,
    confidence NUMERIC(18,8) NOT NULL,
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_adjustments (
    id BIGSERIAL PRIMARY KEY,
    adjustment_id TEXT NOT NULL UNIQUE,
    adjustment_type TEXT NOT NULL,
    target_module TEXT NOT NULL,
    target_key TEXT,
    current_value TEXT,
    recommended_value TEXT,
    reason TEXT NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence NUMERIC(18,8) NOT NULL,
    status TEXT NOT NULL,
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_reviews_market ON trade_reviews (market_id);
CREATE INDEX IF NOT EXISTS idx_trade_reviews_engine ON trade_reviews (engine);
CREATE INDEX IF NOT EXISTS idx_trade_reviews_status ON trade_reviews (review_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signal_performance_source ON signal_performance (source_type, signal_type, market_id);
CREATE INDEX IF NOT EXISTS idx_engine_learning_engine_family ON engine_learning (engine, market_family);
CREATE INDEX IF NOT EXISTS idx_source_learning_source ON source_learning (source_type, source_name);
CREATE INDEX IF NOT EXISTS idx_whale_learning_whale ON whale_learning (whale_id);
CREATE INDEX IF NOT EXISTS idx_ai_learning_model_task ON ai_learning (model_name, task_type);
CREATE INDEX IF NOT EXISTS idx_no_trade_learning_band_engine ON no_trade_learning (regret_band, candidate_engine);
CREATE INDEX IF NOT EXISTS idx_model_adjustments_status_module ON model_adjustments (status, target_module);
