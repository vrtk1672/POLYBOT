-- V2.12 Strategy Router + Engines.
-- Strategy contracts only. No orders, order intents, exit intents, or balance mutations.

CREATE TABLE IF NOT EXISTS strategy_route_runs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL UNIQUE,
    market_id text NOT NULL,
    market_slug text NULL,
    market_family text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    opportunity_run_id text NULL,
    opportunity_score_id bigint NULL,
    runtime_mode text NULL,
    input_sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_completeness_score numeric NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    status text NOT NULL DEFAULT 'STARTED',
    error text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_strategy_route_runs_market_id ON strategy_route_runs (market_id);
CREATE INDEX IF NOT EXISTS idx_strategy_route_runs_run_id ON strategy_route_runs (run_id);
CREATE INDEX IF NOT EXISTS idx_strategy_route_runs_created_desc ON strategy_route_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS strategy_routes_v2 (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    market_family text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    selected_engine text NOT NULL,
    route_status text NOT NULL,
    opportunity_score numeric NOT NULL DEFAULT 0,
    score_band text NOT NULL DEFAULT 'LOW',
    route_confidence numeric NOT NULL DEFAULT 0,
    entry_price_max numeric NULL,
    target_exit numeric NULL,
    partial_take_profit numeric NULL,
    stop_loss numeric NULL,
    max_position_size_usd numeric NOT NULL DEFAULT 0,
    max_position_size_contracts numeric NULL,
    max_loss_usd numeric NOT NULL DEFAULT 0,
    max_hold_minutes integer NOT NULL DEFAULT 0,
    entry_mode text NOT NULL DEFAULT 'NONE',
    exit_mode text NOT NULL DEFAULT 'NONE',
    execution_mode text NOT NULL DEFAULT 'CONTRACT_ONLY',
    engine_contract_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    route_reason text NULL,
    risk_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    no_trade_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    cooldown_required boolean NOT NULL DEFAULT false,
    insufficient_data boolean NOT NULL DEFAULT false,
    insufficient_data_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    reproducibility_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_strategy_routes_market_id ON strategy_routes_v2 (market_id);
CREATE INDEX IF NOT EXISTS idx_strategy_routes_run_id ON strategy_routes_v2 (run_id);
CREATE INDEX IF NOT EXISTS idx_strategy_routes_engine ON strategy_routes_v2 (selected_engine);
CREATE INDEX IF NOT EXISTS idx_strategy_routes_status ON strategy_routes_v2 (route_status);
CREATE INDEX IF NOT EXISTS idx_strategy_routes_created_desc ON strategy_routes_v2 (created_at DESC);

CREATE TABLE IF NOT EXISTS engine_decisions (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    engine text NOT NULL,
    eligible boolean NOT NULL DEFAULT false,
    selected boolean NOT NULL DEFAULT false,
    engine_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    entry_conditions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    exit_conditions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    risk_limits_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    position_sizing_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    allowed_market_families_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    forbidden_conditions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    cooldown_triggers_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    expected_hold_minutes integer NOT NULL DEFAULT 0,
    entry_mode text NOT NULL DEFAULT 'NONE',
    exit_mode text NOT NULL DEFAULT 'NONE',
    rejection_reason text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engine_decisions_market_id ON engine_decisions (market_id);
CREATE INDEX IF NOT EXISTS idx_engine_decisions_run_engine ON engine_decisions (run_id, engine);
CREATE INDEX IF NOT EXISTS idx_engine_decisions_selected ON engine_decisions (selected);

CREATE TABLE IF NOT EXISTS engine_rejections (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    engine text NOT NULL,
    rejection_reason text NOT NULL,
    severity text NOT NULL DEFAULT 'WARNING',
    source_type text NOT NULL DEFAULT 'strategy_engine',
    source_id text NULL,
    hard_block boolean NOT NULL DEFAULT false,
    explanation text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engine_rejections_market_id ON engine_rejections (market_id);
CREATE INDEX IF NOT EXISTS idx_engine_rejections_run_id ON engine_rejections (run_id);
CREATE INDEX IF NOT EXISTS idx_engine_rejections_engine ON engine_rejections (engine);
CREATE INDEX IF NOT EXISTS idx_engine_rejections_reason ON engine_rejections (rejection_reason);

CREATE TABLE IF NOT EXISTS engine_cooldowns (
    id bigserial PRIMARY KEY,
    engine text NOT NULL,
    market_id text NULL,
    market_family text NULL,
    cooldown_type text NOT NULL,
    reason text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NULL,
    active boolean NOT NULL DEFAULT true,
    severity text NOT NULL DEFAULT 'WARNING',
    source_run_id text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engine_cooldowns_engine_active ON engine_cooldowns (engine, active);
CREATE INDEX IF NOT EXISTS idx_engine_cooldowns_market_id ON engine_cooldowns (market_id);
CREATE INDEX IF NOT EXISTS idx_engine_cooldowns_family ON engine_cooldowns (market_family);

