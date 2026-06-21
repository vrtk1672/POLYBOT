-- V2.9 Market Memory V2.
-- Behavioral memory only. No orders, order intents, exits, or execution tables.

CREATE TABLE IF NOT EXISTS market_memory_v2 (
    id bigserial PRIMARY KEY,
    market_id text NOT NULL UNIQUE,
    market_slug text NULL,
    question text NULL,
    market_family text NULL,
    first_seen_at timestamptz NULL,
    last_seen_at timestamptz NULL,
    last_updated_at timestamptz NOT NULL DEFAULT now(),
    observations_count integer NOT NULL DEFAULT 0,
    best_engine text NOT NULL DEFAULT 'UNKNOWN',
    best_engine_confidence numeric NOT NULL DEFAULT 0,
    avg_price numeric NULL,
    avg_spread_bps numeric NULL,
    avg_depth_1c numeric NULL,
    avg_depth_2c numeric NULL,
    avg_depth_5c numeric NULL,
    avg_fill_rate numeric NULL,
    avg_slippage_bps numeric NULL,
    avg_hold_seconds numeric NULL,
    avg_exit_quality numeric NULL,
    avg_time_efficiency numeric NULL,
    false_signal_rate numeric NOT NULL DEFAULT 0,
    technical_block_rate numeric NOT NULL DEFAULT 0,
    liquidity_failure_rate numeric NOT NULL DEFAULT 0,
    stale_data_rate numeric NOT NULL DEFAULT 0,
    wording_risk_avg numeric NULL,
    dispute_risk_avg numeric NULL,
    resolution_delay_avg_seconds numeric NULL,
    news_reaction_score numeric NOT NULL DEFAULT 0,
    social_reaction_score numeric NOT NULL DEFAULT 0,
    whale_reaction_score numeric NOT NULL DEFAULT 0,
    memory_confidence numeric NOT NULL DEFAULT 0,
    memory_status text NOT NULL DEFAULT 'insufficient_data',
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_market_memory_v2_market_id ON market_memory_v2 (market_id);
CREATE INDEX IF NOT EXISTS idx_market_memory_v2_family ON market_memory_v2 (market_family);
CREATE INDEX IF NOT EXISTS idx_market_memory_v2_updated_desc ON market_memory_v2 (updated_at DESC);

CREATE TABLE IF NOT EXISTS market_family_memory (
    id bigserial PRIMARY KEY,
    market_family text NOT NULL,
    category text NOT NULL DEFAULT 'general',
    observations_count integer NOT NULL DEFAULT 0,
    markets_count integer NOT NULL DEFAULT 0,
    best_engine text NOT NULL DEFAULT 'UNKNOWN',
    best_engine_confidence numeric NOT NULL DEFAULT 0,
    avg_spread_bps numeric NULL,
    avg_depth_2c numeric NULL,
    avg_fill_rate numeric NULL,
    avg_slippage_bps numeric NULL,
    avg_hold_seconds numeric NULL,
    strike_win_rate numeric NULL,
    convex_hit_rate numeric NULL,
    maker_adverse_selection_rate numeric NULL,
    safe_engine_success_rate numeric NULL,
    hunt_failure_rate numeric NULL,
    technical_block_rate numeric NOT NULL DEFAULT 0,
    liquidity_failure_rate numeric NOT NULL DEFAULT 0,
    false_signal_rate numeric NOT NULL DEFAULT 0,
    avg_wording_risk numeric NULL,
    avg_resolution_delay_seconds numeric NULL,
    memory_confidence numeric NOT NULL DEFAULT 0,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (market_family, category)
);
CREATE INDEX IF NOT EXISTS idx_market_family_memory_family ON market_family_memory (market_family);
CREATE INDEX IF NOT EXISTS idx_market_family_memory_updated_desc ON market_family_memory (updated_at DESC);

CREATE TABLE IF NOT EXISTS engine_performance_memory (
    id bigserial PRIMARY KEY,
    engine text NOT NULL,
    market_family text NOT NULL DEFAULT 'UNKNOWN',
    market_id text NULL,
    observations_count integer NOT NULL DEFAULT 0,
    wins_count integer NOT NULL DEFAULT 0,
    losses_count integer NOT NULL DEFAULT 0,
    neutral_count integer NOT NULL DEFAULT 0,
    win_rate numeric NOT NULL DEFAULT 0,
    avg_roi numeric NULL,
    avg_roi_per_hour numeric NULL,
    avg_hold_seconds numeric NULL,
    avg_entry_slippage_bps numeric NULL,
    avg_exit_slippage_bps numeric NULL,
    avg_spread_cost_bps numeric NULL,
    avg_fees_bps numeric NULL,
    avg_net_edge_after_costs numeric NULL,
    adverse_selection_rate numeric NOT NULL DEFAULT 0,
    stop_loss_rate numeric NOT NULL DEFAULT 0,
    take_profit_rate numeric NOT NULL DEFAULT 0,
    timeout_rate numeric NOT NULL DEFAULT 0,
    failed_engine_score numeric NOT NULL DEFAULT 0,
    engine_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engine_performance_memory_engine_family ON engine_performance_memory (engine, market_family);
CREATE INDEX IF NOT EXISTS idx_engine_performance_memory_market_id ON engine_performance_memory (market_id);
CREATE INDEX IF NOT EXISTS idx_engine_performance_memory_updated_desc ON engine_performance_memory (updated_at DESC);

CREATE TABLE IF NOT EXISTS source_reliability_memory (
    id bigserial PRIMARY KEY,
    source_type text NOT NULL,
    source_name text NOT NULL,
    source_id text NULL,
    market_family text NULL,
    observations_count integer NOT NULL DEFAULT 0,
    true_positive_count integer NOT NULL DEFAULT 0,
    false_positive_count integer NOT NULL DEFAULT 0,
    false_negative_count integer NOT NULL DEFAULT 0,
    stale_count integer NOT NULL DEFAULT 0,
    duplicate_count integer NOT NULL DEFAULT 0,
    avg_latency_seconds numeric NULL,
    avg_signal_strength numeric NULL,
    avg_market_reaction numeric NULL,
    reliability_score numeric NOT NULL DEFAULT 0.5,
    usefulness_score numeric NOT NULL DEFAULT 0,
    cost_score numeric NULL,
    confidence numeric NOT NULL DEFAULT 0,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_source_reliability_memory_source ON source_reliability_memory (source_type, source_name);
CREATE INDEX IF NOT EXISTS idx_source_reliability_memory_family ON source_reliability_memory (market_family);
CREATE INDEX IF NOT EXISTS idx_source_reliability_memory_updated_desc ON source_reliability_memory (updated_at DESC);

CREATE TABLE IF NOT EXISTS whale_memory (
    id bigserial PRIMARY KEY,
    whale_id text NOT NULL,
    market_family text NULL,
    observations_count integer NOT NULL DEFAULT 0,
    wins_count integer NOT NULL DEFAULT 0,
    losses_count integer NOT NULL DEFAULT 0,
    hit_rate numeric NULL,
    avg_timing_quality numeric NULL,
    avg_entry_quality numeric NULL,
    avg_exit_quality numeric NULL,
    avg_hold_seconds numeric NULL,
    avg_size_usd numeric NULL,
    follow_value_avg numeric NOT NULL DEFAULT 0,
    noise_score_avg numeric NOT NULL DEFAULT 0.5,
    reversal_rate numeric NOT NULL DEFAULT 0,
    late_chase_rate numeric NOT NULL DEFAULT 0,
    market_mover_rate numeric NOT NULL DEFAULT 0,
    whale_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_whale_memory_whale_id ON whale_memory (whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_memory_family ON whale_memory (market_family);
CREATE INDEX IF NOT EXISTS idx_whale_memory_updated_desc ON whale_memory (updated_at DESC);

CREATE TABLE IF NOT EXISTS slippage_memory (
    id bigserial PRIMARY KEY,
    market_id text NULL,
    market_family text NULL,
    token_id text NULL,
    side text NULL,
    observations_count integer NOT NULL DEFAULT 0,
    avg_expected_slippage_bps numeric NULL,
    avg_realized_slippage_bps numeric NULL,
    slippage_error_bps numeric NULL,
    avg_spread_bps numeric NULL,
    avg_depth_2c numeric NULL,
    avg_depth_5c numeric NULL,
    avg_order_size_usd numeric NULL,
    avg_fill_rate numeric NULL,
    failed_fill_rate numeric NOT NULL DEFAULT 0,
    exit_slippage_avg_bps numeric NULL,
    slippage_risk_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_slippage_memory_market_id ON slippage_memory (market_id);
CREATE INDEX IF NOT EXISTS idx_slippage_memory_family ON slippage_memory (market_family);
CREATE INDEX IF NOT EXISTS idx_slippage_memory_token_id ON slippage_memory (token_id);
CREATE INDEX IF NOT EXISTS idx_slippage_memory_updated_desc ON slippage_memory (updated_at DESC);

CREATE TABLE IF NOT EXISTS rules_risk_memory (
    id bigserial PRIMARY KEY,
    market_id text NULL,
    market_family text NULL,
    observations_count integer NOT NULL DEFAULT 0,
    avg_wording_risk numeric NULL,
    avg_dispute_risk numeric NULL,
    avg_resolution_clarity numeric NULL,
    ambiguous_terms_count integer NOT NULL DEFAULT 0,
    edge_case_count integer NOT NULL DEFAULT 0,
    settlement_delay_avg_seconds numeric NULL,
    settlement_dispute_count integer NOT NULL DEFAULT 0,
    rules_block_rate numeric NOT NULL DEFAULT 0,
    rules_risk_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rules_risk_memory_market_id ON rules_risk_memory (market_id);
CREATE INDEX IF NOT EXISTS idx_rules_risk_memory_family ON rules_risk_memory (market_family);
CREATE INDEX IF NOT EXISTS idx_rules_risk_memory_updated_desc ON rules_risk_memory (updated_at DESC);

CREATE TABLE IF NOT EXISTS no_trade_memory (
    id bigserial PRIMARY KEY,
    market_id text NULL,
    market_family text NULL,
    candidate_engine text NULL,
    reason text NOT NULL,
    observations_count integer NOT NULL DEFAULT 0,
    correct_no_trade_count integer NOT NULL DEFAULT 0,
    regret_count integer NOT NULL DEFAULT 0,
    regret_rate numeric NOT NULL DEFAULT 0,
    avg_would_have_roi numeric NULL,
    avg_would_have_drawdown numeric NULL,
    avg_would_have_slippage_bps numeric NULL,
    most_common_block_reason text NULL,
    no_trade_quality_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_no_trade_memory_market_id ON no_trade_memory (market_id);
CREATE INDEX IF NOT EXISTS idx_no_trade_memory_family ON no_trade_memory (market_family);
CREATE INDEX IF NOT EXISTS idx_no_trade_memory_updated_desc ON no_trade_memory (updated_at DESC);
