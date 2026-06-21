-- V2.8 Market / Orderbook / Liquidity / Time / Fees technical neurons.
-- Signal tables only: no execution, order, order intent, or exit tables.

CREATE TABLE IF NOT EXISTS market_technical_signals (
    id bigserial PRIMARY KEY,
    market_id text NOT NULL,
    question text NULL,
    market_slug text NULL,
    ts timestamptz NOT NULL DEFAULT now(),
    price_yes numeric NULL,
    price_no numeric NULL,
    price_change_1m numeric NOT NULL DEFAULT 0,
    price_change_5m numeric NOT NULL DEFAULT 0,
    price_change_15m numeric NOT NULL DEFAULT 0,
    price_change_1h numeric NOT NULL DEFAULT 0,
    volume_1h numeric NOT NULL DEFAULT 0,
    volume_24h numeric NOT NULL DEFAULT 0,
    volatility_score numeric NOT NULL DEFAULT 0,
    momentum_score numeric NOT NULL DEFAULT 0,
    trend_direction text NOT NULL DEFAULT 'UNKNOWN',
    trend_strength numeric NOT NULL DEFAULT 0,
    candle_summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    market_regime text NOT NULL DEFAULT 'unknown',
    data_completeness_score numeric NOT NULL DEFAULT 0,
    stale boolean NOT NULL DEFAULT false,
    technical_score numeric NOT NULL DEFAULT 0,
    technical_blocked boolean NOT NULL DEFAULT false,
    block_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    source text NOT NULL DEFAULT 'v2.8',
    raw_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_technical_signals_market_id ON market_technical_signals (market_id);
CREATE INDEX IF NOT EXISTS idx_market_technical_signals_ts_desc ON market_technical_signals (ts DESC);
CREATE INDEX IF NOT EXISTS idx_market_technical_signals_score ON market_technical_signals (technical_score DESC);
CREATE INDEX IF NOT EXISTS idx_market_technical_signals_blocked ON market_technical_signals (technical_blocked);

CREATE TABLE IF NOT EXISTS orderbook_signals (
    id bigserial PRIMARY KEY,
    market_id text NOT NULL,
    token_id text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    ts timestamptz NOT NULL DEFAULT now(),
    best_bid numeric NULL,
    best_ask numeric NULL,
    mid_price numeric NULL,
    spread numeric NULL,
    spread_bps numeric NULL,
    depth_1c numeric NOT NULL DEFAULT 0,
    depth_2c numeric NOT NULL DEFAULT 0,
    depth_5c numeric NOT NULL DEFAULT 0,
    bid_depth_total numeric NOT NULL DEFAULT 0,
    ask_depth_total numeric NOT NULL DEFAULT 0,
    imbalance_score numeric NOT NULL DEFAULT 0.5,
    queue_quality_score numeric NOT NULL DEFAULT 0,
    cancel_burst_score numeric NOT NULL DEFAULT 0,
    microstructure_score numeric NOT NULL DEFAULT 0,
    orderbook_quality_score numeric NOT NULL DEFAULT 0,
    has_bid_ask boolean NOT NULL DEFAULT false,
    stale boolean NOT NULL DEFAULT false,
    block_reason text NULL,
    source text NOT NULL DEFAULT 'v2.8',
    raw_orderbook_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orderbook_signals_market_id ON orderbook_signals (market_id);
CREATE INDEX IF NOT EXISTS idx_orderbook_signals_ts_desc ON orderbook_signals (ts DESC);
CREATE INDEX IF NOT EXISTS idx_orderbook_signals_token_id ON orderbook_signals (token_id);

CREATE TABLE IF NOT EXISTS liquidity_signals (
    id bigserial PRIMARY KEY,
    market_id text NOT NULL,
    token_id text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    ts timestamptz NOT NULL DEFAULT now(),
    expected_fill_score numeric NOT NULL DEFAULT 0,
    expected_slippage_bps numeric NOT NULL DEFAULT 0,
    expected_slippage_usd numeric NOT NULL DEFAULT 0,
    exit_quality_score numeric NOT NULL DEFAULT 0,
    max_safe_size_usd numeric NOT NULL DEFAULT 0,
    max_safe_size_contracts numeric NOT NULL DEFAULT 0,
    liquidity_decay_score numeric NOT NULL DEFAULT 0,
    entry_liquidity_score numeric NOT NULL DEFAULT 0,
    exit_liquidity_score numeric NOT NULL DEFAULT 0,
    liquidity_block_reason text NULL,
    source text NOT NULL DEFAULT 'v2.8',
    raw_liquidity_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_liquidity_signals_market_id ON liquidity_signals (market_id);
CREATE INDEX IF NOT EXISTS idx_liquidity_signals_ts_desc ON liquidity_signals (ts DESC);
CREATE INDEX IF NOT EXISTS idx_liquidity_signals_token_id ON liquidity_signals (token_id);

CREATE TABLE IF NOT EXISTS time_signals (
    id bigserial PRIMARY KEY,
    market_id text NOT NULL,
    ts timestamptz NOT NULL DEFAULT now(),
    market_close_time timestamptz NULL,
    time_to_close_seconds integer NULL,
    expected_hold_seconds integer NOT NULL DEFAULT 0,
    lockup_penalty_score numeric NOT NULL DEFAULT 0,
    urgency_score numeric NOT NULL DEFAULT 0,
    roi_per_hour_reference numeric NULL,
    time_efficiency_score numeric NOT NULL DEFAULT 0,
    ttl_bucket text NOT NULL DEFAULT 'unknown',
    block_reason text NULL,
    source text NOT NULL DEFAULT 'v2.8',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_time_signals_market_id ON time_signals (market_id);
CREATE INDEX IF NOT EXISTS idx_time_signals_ts_desc ON time_signals (ts DESC);

CREATE TABLE IF NOT EXISTS fee_reward_signals (
    id bigserial PRIMARY KEY,
    market_id text NOT NULL,
    token_id text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    ts timestamptz NOT NULL DEFAULT now(),
    maker_cost_bps numeric NOT NULL DEFAULT 0,
    taker_cost_bps numeric NOT NULL DEFAULT 0,
    spread_cost_bps numeric NOT NULL DEFAULT 0,
    slippage_cost_bps numeric NOT NULL DEFAULT 0,
    reward_pool_usd numeric NOT NULL DEFAULT 0,
    reward_score numeric NOT NULL DEFAULT 0,
    net_edge_after_costs numeric NOT NULL DEFAULT 0,
    fee_penalty_score numeric NOT NULL DEFAULT 0,
    friction_score numeric NOT NULL DEFAULT 0,
    block_reason text NULL,
    source text NOT NULL DEFAULT 'v2.8',
    raw_fee_reward_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fee_reward_signals_market_id ON fee_reward_signals (market_id);
CREATE INDEX IF NOT EXISTS idx_fee_reward_signals_ts_desc ON fee_reward_signals (ts DESC);
CREATE INDEX IF NOT EXISTS idx_fee_reward_signals_token_id ON fee_reward_signals (token_id);

