CREATE TABLE IF NOT EXISTS context_brain_runs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL UNIQUE,
    market_id text NOT NULL,
    market_slug text NULL,
    market_family text NULL,
    run_type text NOT NULL DEFAULT 'CONTEXT_ANALYSIS',
    runtime_mode text NULL,
    input_sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_completeness_score numeric NOT NULL DEFAULT 0,
    memory_confidence numeric NOT NULL DEFAULT 0,
    ai_used boolean NOT NULL DEFAULT false,
    ai_request_id text NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    status text NOT NULL DEFAULT 'STARTED',
    error text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_context_brain_runs_market ON context_brain_runs (market_id);
CREATE INDEX IF NOT EXISTS idx_context_brain_runs_created_desc ON context_brain_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS context_brain_outputs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    market_family text NULL,
    context_shift boolean NOT NULL DEFAULT false,
    direction text NOT NULL DEFAULT 'UNKNOWN',
    strength numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    already_priced_in_score numeric NOT NULL DEFAULT 0,
    ttl_seconds integer NOT NULL DEFAULT 0,
    urgency_score numeric NOT NULL DEFAULT 0,
    risk_score numeric NOT NULL DEFAULT 0,
    risks_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    supporting_signals_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    contradicting_signals_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    memory_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ai_context_summary text NULL,
    explanation text NULL,
    insufficient_data boolean NOT NULL DEFAULT false,
    insufficient_data_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_context_brain_outputs_market ON context_brain_outputs (market_id);
CREATE INDEX IF NOT EXISTS idx_context_brain_outputs_created_desc ON context_brain_outputs (created_at DESC);

CREATE TABLE IF NOT EXISTS capital_brain_runs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL UNIQUE,
    market_id text NULL,
    market_family text NULL,
    candidate_engine text NULL,
    runtime_mode text NULL,
    input_sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_completeness_score numeric NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    status text NOT NULL DEFAULT 'STARTED',
    error text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_capital_brain_runs_market ON capital_brain_runs (market_id);
CREATE INDEX IF NOT EXISTS idx_capital_brain_runs_created_desc ON capital_brain_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS capital_brain_outputs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NULL,
    market_family text NULL,
    candidate_engine text NULL,
    capital_allowed boolean NOT NULL DEFAULT false,
    block_reason text NULL,
    max_position_size_usd numeric NULL,
    max_position_size_contracts numeric NULL,
    risk_budget_usd numeric NULL,
    capital_bucket text NULL,
    cash_reserve_after_usd numeric NULL,
    available_capital_usd numeric NULL,
    locked_capital_usd numeric NULL,
    open_exposure_usd numeric NULL,
    engine_budget_remaining_usd numeric NULL,
    capital_recycling_score numeric NOT NULL DEFAULT 0,
    allocation_confidence numeric NOT NULL DEFAULT 0,
    allocation_reason text NULL,
    constraints_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    insufficient_data boolean NOT NULL DEFAULT false,
    insufficient_data_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_capital_brain_outputs_market ON capital_brain_outputs (market_id);
CREATE INDEX IF NOT EXISTS idx_capital_brain_outputs_created_desc ON capital_brain_outputs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_capital_brain_outputs_engine ON capital_brain_outputs (candidate_engine);
