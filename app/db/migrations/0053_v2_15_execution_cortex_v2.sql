CREATE TABLE IF NOT EXISTS orders_v2 (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    market_family TEXT,
    side TEXT NOT NULL,
    token_id TEXT,
    engine TEXT NOT NULL,
    order_type TEXT NOT NULL,
    execution_mode TEXT NOT NULL CHECK (execution_mode IN ('PAPER_SIM','SHADOW_PLAN')),
    order_status TEXT NOT NULL,
    strategy_route_id BIGINT,
    allocation_id TEXT,
    risk_gate_run_id TEXT,
    risk_decision_id BIGINT,
    exit_plan_id TEXT NOT NULL,
    price NUMERIC(18,8) NOT NULL,
    size NUMERIC(18,8) NOT NULL,
    size_usd NUMERIC(18,8) NOT NULL,
    remaining_size NUMERIC(18,8) NOT NULL DEFAULT 0,
    filled_size NUMERIC(18,8) NOT NULL DEFAULT 0,
    avg_fill_price NUMERIC(18,8),
    max_slippage_bps NUMERIC(18,8) NOT NULL DEFAULT 0,
    ttl_seconds INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ,
    cancel_if_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    orderbook_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    liquidity_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    fee_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_from TEXT NOT NULL DEFAULT 'execution_v2',
    dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT orders_v2_no_live_mode CHECK (execution_mode <> 'LIVE' AND execution_mode <> 'LIVE_SEND' AND execution_mode <> 'REAL_ORDER')
);

CREATE TABLE IF NOT EXISTS order_events_v2 (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    reason TEXT NOT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fills_v2 (
    id BIGSERIAL PRIMARY KEY,
    fill_id TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    fill_mode TEXT NOT NULL CHECK (fill_mode IN ('PAPER_SIM','SHADOW_ESTIMATE')),
    fill_status TEXT NOT NULL,
    requested_size NUMERIC(18,8) NOT NULL,
    filled_size NUMERIC(18,8) NOT NULL,
    fill_price NUMERIC(18,8) NOT NULL,
    expected_price NUMERIC(18,8) NOT NULL,
    slippage_bps NUMERIC(18,8) NOT NULL,
    fee_bps NUMERIC(18,8) NOT NULL DEFAULT 0,
    fee_usd NUMERIC(18,8) NOT NULL DEFAULT 0,
    fill_probability NUMERIC(18,8) NOT NULL DEFAULT 0,
    liquidity_consumed_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    partial BOOLEAN NOT NULL DEFAULT FALSE,
    failed_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS execution_errors (
    id BIGSERIAL PRIMARY KEY,
    error_id TEXT NOT NULL UNIQUE,
    market_id TEXT,
    order_id TEXT,
    error_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    recoverable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS execution_latency (
    id BIGSERIAL PRIMARY KEY,
    latency_id TEXT NOT NULL UNIQUE,
    order_id TEXT,
    market_id TEXT,
    stage TEXT NOT NULL,
    latency_ms NUMERIC(18,8) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS execution_quality (
    id BIGSERIAL PRIMARY KEY,
    quality_id TEXT NOT NULL UNIQUE,
    order_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    expected_fill_price NUMERIC(18,8) NOT NULL,
    actual_fill_price NUMERIC(18,8),
    expected_slippage_bps NUMERIC(18,8) NOT NULL,
    actual_slippage_bps NUMERIC(18,8),
    expected_fill_probability NUMERIC(18,8) NOT NULL,
    actual_fill_ratio NUMERIC(18,8) NOT NULL,
    cancel_count INTEGER NOT NULL DEFAULT 0,
    failed_fill_count INTEGER NOT NULL DEFAULT 0,
    partial_fill_count INTEGER NOT NULL DEFAULT 0,
    execution_quality_score NUMERIC(18,8) NOT NULL,
    quality_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_v2_market ON orders_v2 (market_id);
CREATE INDEX IF NOT EXISTS idx_orders_v2_status ON orders_v2 (order_status);
CREATE INDEX IF NOT EXISTS idx_orders_v2_mode ON orders_v2 (execution_mode);
CREATE INDEX IF NOT EXISTS idx_orders_v2_created ON orders_v2 (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fills_v2_order ON fills_v2 (order_id);
CREATE INDEX IF NOT EXISTS idx_fills_v2_market ON fills_v2 (market_id);
CREATE INDEX IF NOT EXISTS idx_order_events_v2_order ON order_events_v2 (order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_execution_errors_type ON execution_errors (error_type, severity);
CREATE INDEX IF NOT EXISTS idx_execution_quality_order ON execution_quality (order_id);
