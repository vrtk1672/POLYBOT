-- V2.11 Opportunity Cortex.
-- Scoring and candidate-generation only. No orders, order intents, exits, or balance mutations.

CREATE TABLE IF NOT EXISTS opportunity_runs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL UNIQUE,
    market_id text NOT NULL,
    market_slug text NULL,
    market_family text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    runtime_mode text NULL,
    input_sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    input_completeness_score numeric NOT NULL DEFAULT 0,
    context_run_id text NULL,
    capital_run_id text NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    status text NOT NULL DEFAULT 'STARTED',
    error text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opportunity_runs_market_id ON opportunity_runs (market_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_runs_run_id ON opportunity_runs (run_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_runs_created_desc ON opportunity_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS opportunity_scores_v2 (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    market_family text NULL,
    side text NOT NULL DEFAULT 'UNKNOWN',
    opportunity_score numeric NOT NULL DEFAULT 0,
    score_band text NOT NULL DEFAULT 'LOW',
    edge numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    trigger_strength numeric NOT NULL DEFAULT 0,
    repricing_potential numeric NOT NULL DEFAULT 0,
    time_efficiency numeric NOT NULL DEFAULT 0,
    liquidity_quality numeric NOT NULL DEFAULT 0,
    exit_probability numeric NOT NULL DEFAULT 0,
    capital_recycling_speed numeric NOT NULL DEFAULT 0,
    convexity numeric NOT NULL DEFAULT 0,
    balance_fit numeric NOT NULL DEFAULT 0,
    fee_reward_advantage numeric NOT NULL DEFAULT 0,
    risk_penalty numeric NOT NULL DEFAULT 0,
    slippage_penalty numeric NOT NULL DEFAULT 0,
    lockup_penalty numeric NOT NULL DEFAULT 0,
    correlation_risk numeric NOT NULL DEFAULT 0,
    trap_risk numeric NOT NULL DEFAULT 0,
    wording_risk numeric NOT NULL DEFAULT 0,
    adverse_selection_risk numeric NOT NULL DEFAULT 0,
    already_priced_in_score numeric NOT NULL DEFAULT 0,
    technical_blocked boolean NOT NULL DEFAULT false,
    capital_allowed boolean NOT NULL DEFAULT false,
    insufficient_data boolean NOT NULL DEFAULT false,
    insufficient_data_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    candidate_engines_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    no_trade_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    explanation text NULL,
    reproducibility_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opportunity_scores_market_id ON opportunity_scores_v2 (market_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_scores_run_id ON opportunity_scores_v2 (run_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_scores_score_desc ON opportunity_scores_v2 (opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_scores_created_desc ON opportunity_scores_v2 (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_scores_band ON opportunity_scores_v2 (score_band);

CREATE TABLE IF NOT EXISTS opportunity_signal_inputs (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    source_type text NOT NULL,
    source_id text NULL,
    source_run_id text NULL,
    input_name text NOT NULL,
    input_value_numeric numeric NULL,
    input_value_text text NULL,
    input_json jsonb NULL,
    weight numeric NOT NULL DEFAULT 0,
    contribution numeric NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opportunity_signal_inputs_market_id ON opportunity_signal_inputs (market_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_signal_inputs_run_id ON opportunity_signal_inputs (run_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_signal_inputs_source_type ON opportunity_signal_inputs (source_type);

CREATE TABLE IF NOT EXISTS opportunity_risk_flags (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    market_id text NOT NULL,
    risk_flag text NOT NULL,
    severity text NOT NULL DEFAULT 'WARNING',
    source_type text NOT NULL,
    source_id text NULL,
    penalty numeric NOT NULL DEFAULT 0,
    blocks_opportunity boolean NOT NULL DEFAULT false,
    explanation text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opportunity_risk_flags_market_id ON opportunity_risk_flags (market_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_risk_flags_run_id ON opportunity_risk_flags (run_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_risk_flags_flag ON opportunity_risk_flags (risk_flag);
CREATE INDEX IF NOT EXISTS idx_opportunity_risk_flags_severity ON opportunity_risk_flags (severity);

