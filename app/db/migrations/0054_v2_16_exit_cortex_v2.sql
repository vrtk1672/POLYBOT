CREATE TABLE IF NOT EXISTS exit_plans (
    id BIGSERIAL PRIMARY KEY,
    exit_plan_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    market_family TEXT,
    side TEXT NOT NULL,
    engine TEXT NOT NULL,
    strategy_route_id BIGINT,
    allocation_id TEXT,
    risk_gate_run_id TEXT,
    order_id TEXT,
    position_ref TEXT,
    entry_price NUMERIC(18,8),
    entry_size NUMERIC(18,8),
    target_exit NUMERIC(18,8),
    partial_take_profit NUMERIC(18,8),
    partial_take_profit_pct NUMERIC(18,8),
    stop_loss NUMERIC(18,8),
    max_hold_seconds INTEGER,
    invalidation_rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    liquidity_exit_check_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    emergency_exit_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    momentum_decay_exit_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    spread_exit_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    news_invalidated_exit_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    exit_mode TEXT NOT NULL CHECK (exit_mode IN ('PAPER_SIM_EXIT','SHADOW_EXIT_PLAN')),
    plan_status TEXT NOT NULL,
    created_from TEXT NOT NULL DEFAULT 'exit_cortex_v2',
    data_confidence NUMERIC(18,8) NOT NULL DEFAULT 0,
    insufficient_data BOOLEAN NOT NULL DEFAULT FALSE,
    insufficient_data_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT exit_plans_no_live_mode CHECK (exit_mode <> 'LIVE_EXIT' AND exit_mode <> 'LIVE_SEND')
);

CREATE TABLE IF NOT EXISTS exit_intents (
    id BIGSERIAL PRIMARY KEY,
    exit_intent_id TEXT NOT NULL UNIQUE,
    exit_plan_id TEXT NOT NULL,
    order_id TEXT,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    exit_side TEXT NOT NULL,
    reason TEXT NOT NULL,
    intent_status TEXT NOT NULL,
    exit_price_target NUMERIC(18,8),
    exit_size NUMERIC(18,8) NOT NULL,
    exit_size_pct NUMERIC(18,8),
    max_slippage_bps NUMERIC(18,8) NOT NULL DEFAULT 0,
    urgency TEXT NOT NULL,
    execution_mode TEXT NOT NULL CHECK (execution_mode IN ('PAPER_SIM_EXIT','SHADOW_EXIT_PLAN')),
    paper_shadow_only BOOLEAN NOT NULL DEFAULT TRUE,
    risk_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    liquidity_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    trigger_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT exit_intents_internal_only CHECK (paper_shadow_only IS TRUE)
);

CREATE TABLE IF NOT EXISTS exit_events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    exit_plan_id TEXT,
    exit_intent_id TEXT,
    order_id TEXT,
    market_id TEXT,
    event_type TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    reason TEXT NOT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exit_quality (
    id BIGSERIAL PRIMARY KEY,
    quality_id TEXT NOT NULL UNIQUE,
    exit_plan_id TEXT NOT NULL,
    exit_intent_id TEXT,
    order_id TEXT,
    market_id TEXT NOT NULL,
    expected_exit_price NUMERIC(18,8) NOT NULL,
    actual_exit_price NUMERIC(18,8),
    expected_slippage_bps NUMERIC(18,8) NOT NULL,
    actual_slippage_bps NUMERIC(18,8),
    expected_exit_liquidity_score NUMERIC(18,8) NOT NULL,
    actual_exit_fill_ratio NUMERIC(18,8),
    exit_latency_ms NUMERIC(18,8),
    exit_quality_score NUMERIC(18,8) NOT NULL,
    quality_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exit_failures (
    id BIGSERIAL PRIMARY KEY,
    failure_id TEXT NOT NULL UNIQUE,
    exit_plan_id TEXT,
    exit_intent_id TEXT,
    order_id TEXT,
    market_id TEXT,
    failure_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    reason TEXT NOT NULL,
    recoverable BOOLEAN NOT NULL DEFAULT TRUE,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exit_plans_market ON exit_plans (market_id);
CREATE INDEX IF NOT EXISTS idx_exit_plans_order ON exit_plans (order_id);
CREATE INDEX IF NOT EXISTS idx_exit_plans_status ON exit_plans (plan_status);
CREATE INDEX IF NOT EXISTS idx_exit_plans_created ON exit_plans (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exit_intents_plan ON exit_intents (exit_plan_id);
CREATE INDEX IF NOT EXISTS idx_exit_intents_status_reason ON exit_intents (intent_status, reason);
CREATE INDEX IF NOT EXISTS idx_exit_events_plan_created ON exit_events (exit_plan_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exit_events_created ON exit_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exit_failures_type_severity ON exit_failures (failure_type, severity);
CREATE INDEX IF NOT EXISTS idx_exit_quality_plan ON exit_quality (exit_plan_id);
