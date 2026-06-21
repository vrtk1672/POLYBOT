-- V2.14 Risk Gate + Risk Governor.
-- Risk approval/blocking records only. No orders, order intents, exits, or balance mutations.

CREATE TABLE IF NOT EXISTS risk_gate_runs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL UNIQUE,
    market_id text NOT NULL,
    market_family text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    engine text NOT NULL DEFAULT 'NO_TRADE',
    strategy_route_id bigint NULL,
    allocation_id text NULL,
    runtime_mode text NULL,
    input_sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_completeness_score numeric NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    status text NOT NULL DEFAULT 'STARTED',
    error text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_gate_runs_market_id ON risk_gate_runs (market_id);
CREATE INDEX IF NOT EXISTS idx_risk_gate_runs_run_id ON risk_gate_runs (run_id);
CREATE INDEX IF NOT EXISTS idx_risk_gate_runs_created_desc ON risk_gate_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS risk_gate_decisions (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    market_family text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    engine text NOT NULL DEFAULT 'NO_TRADE',
    decision text NOT NULL,
    approved boolean NOT NULL DEFAULT false,
    blocked boolean NOT NULL DEFAULT false,
    risk_score numeric NOT NULL DEFAULT 0,
    max_loss_usd numeric NOT NULL DEFAULT 0,
    approved_max_loss_usd numeric NOT NULL DEFAULT 0,
    approved_position_size_usd numeric NOT NULL DEFAULT 0,
    liquidity_ok boolean NOT NULL DEFAULT true,
    slippage_ok boolean NOT NULL DEFAULT true,
    wording_risk_ok boolean NOT NULL DEFAULT true,
    correlation_ok boolean NOT NULL DEFAULT true,
    exposure_ok boolean NOT NULL DEFAULT true,
    engine_budget_ok boolean NOT NULL DEFAULT true,
    confidence_ok boolean NOT NULL DEFAULT true,
    exit_plan_ok boolean NOT NULL DEFAULT true,
    governor_ok boolean NOT NULL DEFAULT true,
    block_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    warnings_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    constraints_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    manual_override_used boolean NOT NULL DEFAULT false,
    override_id text NULL,
    explanation text NULL,
    reproducibility_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_gate_decisions_market_id ON risk_gate_decisions (market_id);
CREATE INDEX IF NOT EXISTS idx_risk_gate_decisions_engine ON risk_gate_decisions (engine);
CREATE INDEX IF NOT EXISTS idx_risk_gate_decisions_decision ON risk_gate_decisions (decision);
CREATE INDEX IF NOT EXISTS idx_risk_gate_decisions_created_desc ON risk_gate_decisions (created_at DESC);

CREATE TABLE IF NOT EXISTS risk_governor_state (
    id bigserial PRIMARY KEY,
    state_id text NOT NULL UNIQUE,
    runtime_mode text NULL,
    governor_status text NOT NULL,
    kill_switch_active boolean NOT NULL DEFAULT false,
    attack_mode_allowed boolean NOT NULL DEFAULT false,
    cooldown_active boolean NOT NULL DEFAULT false,
    daily_pnl_usd numeric NOT NULL DEFAULT 0,
    weekly_pnl_usd numeric NOT NULL DEFAULT 0,
    daily_loss_usd numeric NOT NULL DEFAULT 0,
    weekly_loss_usd numeric NOT NULL DEFAULT 0,
    open_positions_count integer NOT NULL DEFAULT 0,
    open_exposure_usd numeric NOT NULL DEFAULT 0,
    max_daily_loss_usd numeric NOT NULL DEFAULT 0,
    max_weekly_loss_usd numeric NOT NULL DEFAULT 0,
    max_open_positions integer NOT NULL DEFAULT 0,
    max_total_exposure_usd numeric NOT NULL DEFAULT 0,
    max_engine_loss_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    max_market_family_exposure_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    active_cooldowns_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    active_breaches_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    manual_overrides_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    data_confidence numeric NOT NULL DEFAULT 0,
    insufficient_data boolean NOT NULL DEFAULT false,
    insufficient_data_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_governor_state_status ON risk_governor_state (governor_status);
CREATE INDEX IF NOT EXISTS idx_risk_governor_state_updated_desc ON risk_governor_state (updated_at DESC);

CREATE TABLE IF NOT EXISTS risk_governor_events (
    id bigserial PRIMARY KEY,
    event_id text NOT NULL UNIQUE,
    event_type text NOT NULL,
    old_status text NULL,
    new_status text NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    correlation_id text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_governor_events_event_type ON risk_governor_events (event_type);
CREATE INDEX IF NOT EXISTS idx_risk_governor_events_created_desc ON risk_governor_events (created_at DESC);

CREATE TABLE IF NOT EXISTS risk_limits (
    id bigserial PRIMARY KEY,
    limit_id text NOT NULL UNIQUE,
    scope text NOT NULL,
    scope_key text NULL,
    limit_type text NOT NULL,
    limit_value_usd numeric NULL,
    limit_value_pct numeric NULL,
    limit_value_count integer NULL,
    enabled boolean NOT NULL DEFAULT true,
    hard_limit boolean NOT NULL DEFAULT true,
    policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_limits_scope ON risk_limits (scope, scope_key);
CREATE INDEX IF NOT EXISTS idx_risk_limits_type ON risk_limits (limit_type);

CREATE TABLE IF NOT EXISTS risk_breaches (
    id bigserial PRIMARY KEY,
    breach_id text NOT NULL UNIQUE,
    limit_id text NULL,
    breach_type text NOT NULL,
    severity text NOT NULL DEFAULT 'WARNING',
    market_id text NULL,
    market_family text NULL,
    engine text NULL,
    observed_value numeric NOT NULL DEFAULT 0,
    limit_value numeric NOT NULL DEFAULT 0,
    blocked boolean NOT NULL DEFAULT false,
    cooldown_created boolean NOT NULL DEFAULT false,
    explanation text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_risk_breaches_type ON risk_breaches (breach_type);
CREATE INDEX IF NOT EXISTS idx_risk_breaches_severity ON risk_breaches (severity);
CREATE INDEX IF NOT EXISTS idx_risk_breaches_created_desc ON risk_breaches (created_at DESC);

CREATE TABLE IF NOT EXISTS cooldown_events (
    id bigserial PRIMARY KEY,
    cooldown_id text NOT NULL UNIQUE,
    scope text NOT NULL,
    scope_key text NULL,
    engine text NULL,
    market_family text NULL,
    market_id text NULL,
    reason text NOT NULL,
    severity text NOT NULL DEFAULT 'WARNING',
    started_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NULL,
    active boolean NOT NULL DEFAULT true,
    source_breach_id text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cooldown_events_active_scope ON cooldown_events (active, scope);
CREATE INDEX IF NOT EXISTS idx_cooldown_events_engine ON cooldown_events (engine);
CREATE INDEX IF NOT EXISTS idx_cooldown_events_family ON cooldown_events (market_family);

