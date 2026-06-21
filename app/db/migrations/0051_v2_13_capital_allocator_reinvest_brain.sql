-- V2.13 Capital Allocator V2 + Reinvest Brain.
-- Internal capital accounting only. No orders, order intents, exits, or external balance mutations.

CREATE TABLE IF NOT EXISTS capital_state_v2 (
    id bigserial PRIMARY KEY,
    state_id text NOT NULL UNIQUE,
    runtime_mode text NULL,
    total_capital_usd numeric NOT NULL DEFAULT 0,
    base_capital_usd numeric NOT NULL DEFAULT 0,
    available_capital_usd numeric NOT NULL DEFAULT 0,
    locked_capital_usd numeric NOT NULL DEFAULT 0,
    open_exposure_usd numeric NOT NULL DEFAULT 0,
    survival_reserve_usd numeric NOT NULL DEFAULT 0,
    cash_reserve_usd numeric NOT NULL DEFAULT 0,
    profit_pocket_usd numeric NOT NULL DEFAULT 0,
    attack_bank_usd numeric NOT NULL DEFAULT 0,
    realized_pnl_usd numeric NOT NULL DEFAULT 0,
    unrealized_pnl_usd numeric NULL,
    daily_pnl_usd numeric NULL,
    weekly_pnl_usd numeric NULL,
    loss_streak_count integer NOT NULL DEFAULT 0,
    win_streak_count integer NOT NULL DEFAULT 0,
    source_type text NOT NULL DEFAULT 'UNKNOWN',
    source_ref text NULL,
    data_confidence numeric NOT NULL DEFAULT 0,
    insufficient_data boolean NOT NULL DEFAULT false,
    insufficient_data_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_capital_state_created_desc ON capital_state_v2 (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_capital_state_source ON capital_state_v2 (source_type);

CREATE TABLE IF NOT EXISTS engine_budgets (
    id bigserial PRIMARY KEY,
    engine text NOT NULL,
    bucket text NOT NULL,
    budget_usd numeric NOT NULL DEFAULT 0,
    used_usd numeric NOT NULL DEFAULT 0,
    reserved_usd numeric NOT NULL DEFAULT 0,
    available_usd numeric NOT NULL DEFAULT 0,
    max_position_usd numeric NOT NULL DEFAULT 0,
    max_loss_usd numeric NOT NULL DEFAULT 0,
    max_open_allocations integer NOT NULL DEFAULT 1,
    cooldown_active boolean NOT NULL DEFAULT false,
    loss_streak_multiplier numeric NOT NULL DEFAULT 1,
    enabled boolean NOT NULL DEFAULT true,
    policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (engine, bucket)
);
CREATE INDEX IF NOT EXISTS idx_engine_budgets_engine_bucket ON engine_budgets (engine, bucket);
CREATE INDEX IF NOT EXISTS idx_engine_budgets_enabled ON engine_budgets (enabled);

CREATE TABLE IF NOT EXISTS capital_allocations_v2 (
    id bigserial PRIMARY KEY,
    allocation_id text NOT NULL UNIQUE,
    strategy_run_id text NULL,
    strategy_route_id bigint NULL,
    market_id text NOT NULL,
    market_family text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    engine text NOT NULL,
    bucket text NULL,
    allocation_status text NOT NULL,
    requested_size_usd numeric NOT NULL DEFAULT 0,
    approved_size_usd numeric NOT NULL DEFAULT 0,
    max_loss_usd numeric NOT NULL DEFAULT 0,
    reserve_after_usd numeric NOT NULL DEFAULT 0,
    engine_budget_before_usd numeric NOT NULL DEFAULT 0,
    engine_budget_after_usd numeric NOT NULL DEFAULT 0,
    attack_bank_used_usd numeric NOT NULL DEFAULT 0,
    profit_pocket_used_usd numeric NOT NULL DEFAULT 0,
    base_capital_used_usd numeric NOT NULL DEFAULT 0,
    allocation_reason text NULL,
    rejection_reason text NULL,
    constraints_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    dry_run boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_capital_allocations_market_id ON capital_allocations_v2 (market_id);
CREATE INDEX IF NOT EXISTS idx_capital_allocations_engine ON capital_allocations_v2 (engine);
CREATE INDEX IF NOT EXISTS idx_capital_allocations_bucket ON capital_allocations_v2 (bucket);
CREATE INDEX IF NOT EXISTS idx_capital_allocations_status ON capital_allocations_v2 (allocation_status);
CREATE INDEX IF NOT EXISTS idx_capital_allocations_created_desc ON capital_allocations_v2 (created_at DESC);

CREATE TABLE IF NOT EXISTS reinvest_ledger (
    id bigserial PRIMARY KEY,
    ledger_id text NOT NULL UNIQUE,
    event_type text NOT NULL,
    amount_usd numeric NOT NULL DEFAULT 0,
    from_bucket text NULL,
    to_bucket text NULL,
    source_trade_id text NULL,
    source_allocation_id text NULL,
    realized_profit_usd numeric NULL,
    reason text NULL,
    policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reinvest_ledger_event_type ON reinvest_ledger (event_type);
CREATE INDEX IF NOT EXISTS idx_reinvest_ledger_created_desc ON reinvest_ledger (created_at DESC);

CREATE TABLE IF NOT EXISTS profit_pocket (
    id bigserial PRIMARY KEY,
    pocket_id text NOT NULL UNIQUE,
    total_realized_profit_usd numeric NOT NULL DEFAULT 0,
    available_profit_usd numeric NOT NULL DEFAULT 0,
    reserved_profit_usd numeric NOT NULL DEFAULT 0,
    withdrawn_profit_usd numeric NOT NULL DEFAULT 0,
    reinvested_profit_usd numeric NOT NULL DEFAULT 0,
    source_type text NOT NULL DEFAULT 'INTERNAL',
    source_ref text NULL,
    confidence numeric NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_profit_pocket_updated_desc ON profit_pocket (updated_at DESC);

CREATE TABLE IF NOT EXISTS attack_bank (
    id bigserial PRIMARY KEY,
    attack_bank_id text NOT NULL UNIQUE,
    available_usd numeric NOT NULL DEFAULT 0,
    reserved_usd numeric NOT NULL DEFAULT 0,
    used_usd numeric NOT NULL DEFAULT 0,
    realized_profit_funded_usd numeric NOT NULL DEFAULT 0,
    base_capital_used_usd numeric NOT NULL DEFAULT 0,
    max_attack_allocation_usd numeric NOT NULL DEFAULT 0,
    enabled boolean NOT NULL DEFAULT false,
    policy_json jsonb NOT NULL DEFAULT '{"realized_profit_only": true}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (base_capital_used_usd = 0)
);
CREATE INDEX IF NOT EXISTS idx_attack_bank_updated_desc ON attack_bank (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_attack_bank_enabled ON attack_bank (enabled);

CREATE TABLE IF NOT EXISTS capital_events (
    id bigserial PRIMARY KEY,
    event_id text NOT NULL UNIQUE,
    event_type text NOT NULL,
    actor text NOT NULL,
    market_id text NULL,
    engine text NULL,
    bucket text NULL,
    amount_usd numeric NULL,
    before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    reason text NULL,
    correlation_id text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_capital_events_event_type ON capital_events (event_type);
CREATE INDEX IF NOT EXISTS idx_capital_events_created_desc ON capital_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_capital_events_market_id ON capital_events (market_id);

