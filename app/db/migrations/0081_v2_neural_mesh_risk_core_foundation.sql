ALTER TABLE risk_gate_runs
    ADD COLUMN IF NOT EXISTS thesis_profiles_checked INTEGER NOT NULL DEFAULT 0 CHECK (thesis_profiles_checked >= 0),
    ADD COLUMN IF NOT EXISTS risk_decisions_created INTEGER NOT NULL DEFAULT 0 CHECK (risk_decisions_created >= 0),
    ADD COLUMN IF NOT EXISTS risk_decisions_updated INTEGER NOT NULL DEFAULT 0 CHECK (risk_decisions_updated >= 0),
    ADD COLUMN IF NOT EXISTS approved_count INTEGER NOT NULL DEFAULT 0 CHECK (approved_count >= 0),
    ADD COLUMN IF NOT EXISTS rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    ADD COLUMN IF NOT EXISTS blocked_count INTEGER NOT NULL DEFAULT 0 CHECK (blocked_count >= 0),
    ADD COLUMN IF NOT EXISTS warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    ADD COLUMN IF NOT EXISTS max_position_size_default NUMERIC(18, 6) NOT NULL DEFAULT 10.0,
    ADD COLUMN IF NOT EXISTS max_loss_default NUMERIC(18, 6) NOT NULL DEFAULT 5.0,
    ADD COLUMN IF NOT EXISTS confidence_threshold NUMERIC(10, 6) NOT NULL DEFAULT 0.6,
    ADD COLUMN IF NOT EXISTS paper_ready_before BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS paper_ready_after BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS orders_created INTEGER NOT NULL DEFAULT 0 CHECK (orders_created >= 0),
    ADD COLUMN IF NOT EXISTS order_intents_created INTEGER NOT NULL DEFAULT 0 CHECK (order_intents_created >= 0),
    ADD COLUMN IF NOT EXISTS fills_created INTEGER NOT NULL DEFAULT 0 CHECK (fills_created >= 0),
    ADD COLUMN IF NOT EXISTS positions_created INTEGER NOT NULL DEFAULT 0 CHECK (positions_created >= 0),
    ADD COLUMN IF NOT EXISTS live_actions_created INTEGER NOT NULL DEFAULT 0 CHECK (live_actions_created >= 0),
    ADD COLUMN IF NOT EXISTS error_summary TEXT NULL;

CREATE TABLE IF NOT EXISTS risk_decisions (
    id BIGSERIAL PRIMARY KEY,
    risk_decision_id TEXT NOT NULL UNIQUE,
    thesis_id TEXT NOT NULL,
    market_id TEXT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('APPROVE', 'REJECT', 'BLOCK', 'WARN_ONLY', 'ERROR')),
    risk_status TEXT NOT NULL CHECK (risk_status IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'BLOCKED', 'ERROR')),
    risk_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (risk_score >= 0 AND risk_score <= 1),
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    max_position_size NUMERIC(18, 6) NOT NULL DEFAULT 10.0,
    max_loss NUMERIC(18, 6) NOT NULL DEFAULT 5.0,
    market_risk_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (market_risk_score >= 0 AND market_risk_score <= 1),
    liquidity_risk_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (liquidity_risk_score >= 0 AND liquidity_risk_score <= 1),
    spread_risk_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (spread_risk_score >= 0 AND spread_risk_score <= 1),
    missing_data_risk_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (missing_data_risk_score >= 0 AND missing_data_risk_score <= 1),
    confidence_risk_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (confidence_risk_score >= 0 AND confidence_risk_score <= 1),
    daily_exposure_risk_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (daily_exposure_risk_score >= 0 AND daily_exposure_risk_score <= 1),
    risk_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_missing_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_thesis_status TEXT NULL,
    orderbook_snapshot_id BIGINT NULL,
    paper_candidate_allowed BOOLEAN NOT NULL DEFAULT false CHECK (paper_candidate_allowed = false),
    execution_allowed BOOLEAN NOT NULL DEFAULT false CHECK (execution_allowed = false),
    risk_approved BOOLEAN NOT NULL DEFAULT false,
    exit_required BOOLEAN NOT NULL DEFAULT true,
    generated_by TEXT NOT NULL DEFAULT 'runtime',
    producer_name TEXT NOT NULL DEFAULT 'risk_core',
    is_runtime_generated BOOLEAN NOT NULL DEFAULT true,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_risk_decisions_thesis
    ON risk_decisions (thesis_id);

CREATE INDEX IF NOT EXISTS idx_risk_decisions_market
    ON risk_decisions (market_id)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_risk_decisions_decision
    ON risk_decisions (decision);

CREATE INDEX IF NOT EXISTS idx_risk_decisions_status
    ON risk_decisions (risk_status);

CREATE INDEX IF NOT EXISTS idx_risk_decisions_created
    ON risk_decisions (created_at DESC);

ALTER TABLE risk_limits
    ADD COLUMN IF NOT EXISTS value NUMERIC(18, 6) NULL,
    ADD COLUMN IF NOT EXISTS unit TEXT NULL,
    ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT true;

INSERT INTO risk_limits (
    limit_id, scope, limit_type, limit_value_usd, limit_value_pct,
    limit_value_count, value, unit, enabled, active, hard_limit, policy_json
)
VALUES
    ('risk_core_max_position_size', 'GLOBAL', 'max_position_size', 10.0, NULL, NULL, 10.0, 'paper_units', true, true, true, '{"phase":"4C-P"}'::jsonb),
    ('risk_core_max_loss', 'GLOBAL', 'max_loss', 5.0, NULL, NULL, 5.0, 'paper_units', true, true, true, '{"phase":"4C-P"}'::jsonb),
    ('risk_core_confidence_threshold', 'GLOBAL', 'confidence_threshold', NULL, 0.6, NULL, 0.6, 'ratio', true, true, true, '{"phase":"4C-P"}'::jsonb),
    ('risk_core_max_spread', 'GLOBAL', 'max_spread', NULL, 0.08, NULL, 0.08, 'price', true, true, true, '{"phase":"4C-P"}'::jsonb),
    ('risk_core_min_liquidity_score', 'GLOBAL', 'min_liquidity_score', NULL, 0.25, NULL, 0.25, 'ratio', true, true, true, '{"phase":"4C-P"}'::jsonb),
    ('risk_core_daily_exposure_placeholder', 'GLOBAL', 'daily_exposure_limit', 50.0, NULL, NULL, 50.0, 'paper_units', true, true, true, '{"phase":"4C-P","placeholder":true}'::jsonb)
ON CONFLICT (limit_id) DO UPDATE SET
    limit_value_usd = EXCLUDED.limit_value_usd,
    limit_value_pct = EXCLUDED.limit_value_pct,
    value = EXCLUDED.value,
    unit = EXCLUDED.unit,
    enabled = true,
    active = true,
    updated_at = now();
