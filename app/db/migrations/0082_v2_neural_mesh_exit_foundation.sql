ALTER TABLE exit_plans
    ALTER COLUMN market_id DROP NOT NULL,
    ALTER COLUMN side DROP NOT NULL,
    ALTER COLUMN engine SET DEFAULT 'EXIT_FOUNDATION',
    ALTER COLUMN entry_price SET DEFAULT 0,
    ALTER COLUMN entry_size SET DEFAULT 0,
    ALTER COLUMN exit_mode SET DEFAULT 'PAPER_SIM_EXIT',
    ADD COLUMN IF NOT EXISTS thesis_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS risk_decision_ref TEXT NULL,
    ADD COLUMN IF NOT EXISTS status TEXT NULL,
    ADD COLUMN IF NOT EXISTS exit_type TEXT NULL,
    ADD COLUMN IF NOT EXISTS invalidation_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS emergency_exit_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS liquidity_exit_check JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS time_exit_check JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS missing_exit_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS source_risk_status TEXT NULL,
    ADD COLUMN IF NOT EXISTS source_risk_score NUMERIC(10, 6) NULL,
    ADD COLUMN IF NOT EXISTS orderbook_snapshot_id BIGINT NULL,
    ADD COLUMN IF NOT EXISTS paper_intent_allowed BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS paper_exit_ready BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS execution_allowed BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS generated_by TEXT NOT NULL DEFAULT 'runtime',
    ADD COLUMN IF NOT EXISTS producer_name TEXT NOT NULL DEFAULT 'exit_foundation',
    ADD COLUMN IF NOT EXISTS is_runtime_generated BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS is_dry_run_generated BOOLEAN NOT NULL DEFAULT false;

UPDATE exit_plans
SET status = COALESCE(status,
    CASE
        WHEN plan_status IN ('ACTIVE', 'PENDING_ORDER', 'COMPLETED') THEN 'COMPLETE'
        WHEN plan_status = 'INSUFFICIENT_DATA' THEN 'INCOMPLETE'
        WHEN plan_status IN ('CANCELLED', 'FAILED') THEN 'BLOCKED'
        ELSE 'INCOMPLETE'
    END
),
exit_type = COALESCE(exit_type, 'BASIC_PROTECTIVE_EXIT')
WHERE status IS NULL OR exit_type IS NULL;

ALTER TABLE exit_plans
    ALTER COLUMN status SET DEFAULT 'INCOMPLETE',
    ALTER COLUMN status SET NOT NULL,
    ALTER COLUMN exit_type SET DEFAULT 'BASIC_PROTECTIVE_EXIT',
    ALTER COLUMN exit_type SET NOT NULL;

ALTER TABLE exit_plans
    DROP CONSTRAINT IF EXISTS exit_plans_status_check,
    DROP CONSTRAINT IF EXISTS exit_plans_exit_type_check,
    DROP CONSTRAINT IF EXISTS exit_plans_paper_intent_allowed_false,
    DROP CONSTRAINT IF EXISTS exit_plans_execution_allowed_false;

ALTER TABLE exit_plans
    ADD CONSTRAINT exit_plans_status_check
        CHECK (status IN ('COMPLETE', 'INCOMPLETE', 'BLOCKED', 'ERROR')),
    ADD CONSTRAINT exit_plans_exit_type_check
        CHECK (exit_type IN (
            'BASIC_PROTECTIVE_EXIT',
            'BLOCKED_NO_ENTRY_EXIT',
            'LIQUIDITY_PROTECTION_EXIT',
            'TIME_ONLY_EXIT',
            'EMERGENCY_ONLY_EXIT'
        )),
    ADD CONSTRAINT exit_plans_paper_intent_allowed_false
        CHECK (paper_intent_allowed = false),
    ADD CONSTRAINT exit_plans_execution_allowed_false
        CHECK (execution_allowed = false);

CREATE INDEX IF NOT EXISTS idx_exit_plans_thesis
    ON exit_plans (thesis_id)
    WHERE thesis_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_exit_plans_risk_decision_ref
    ON exit_plans (risk_decision_ref)
    WHERE risk_decision_ref IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_exit_plans_foundation_status
    ON exit_plans (status);

CREATE INDEX IF NOT EXISTS idx_exit_plans_foundation_type
    ON exit_plans (exit_type);

CREATE INDEX IF NOT EXISTS idx_exit_plans_paper_exit_ready
    ON exit_plans (paper_exit_ready);

CREATE TABLE IF NOT EXISTS exit_plan_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    risk_decisions_checked INTEGER NOT NULL DEFAULT 0 CHECK (risk_decisions_checked >= 0),
    exit_plans_created INTEGER NOT NULL DEFAULT 0 CHECK (exit_plans_created >= 0),
    exit_plans_updated INTEGER NOT NULL DEFAULT 0 CHECK (exit_plans_updated >= 0),
    complete_exit_count INTEGER NOT NULL DEFAULT 0 CHECK (complete_exit_count >= 0),
    incomplete_exit_count INTEGER NOT NULL DEFAULT 0 CHECK (incomplete_exit_count >= 0),
    blocked_exit_count INTEGER NOT NULL DEFAULT 0 CHECK (blocked_exit_count >= 0),
    missing_market_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_market_count >= 0),
    missing_orderbook_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_orderbook_count >= 0),
    missing_side_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_side_count >= 0),
    missing_risk_approval_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_risk_approval_count >= 0),
    paper_ready_before BOOLEAN NOT NULL DEFAULT false,
    paper_ready_after BOOLEAN NOT NULL DEFAULT false,
    orders_created INTEGER NOT NULL DEFAULT 0 CHECK (orders_created >= 0),
    order_intents_created INTEGER NOT NULL DEFAULT 0 CHECK (order_intents_created >= 0),
    fills_created INTEGER NOT NULL DEFAULT 0 CHECK (fills_created >= 0),
    positions_created INTEGER NOT NULL DEFAULT 0 CHECK (positions_created >= 0),
    live_actions_created INTEGER NOT NULL DEFAULT 0 CHECK (live_actions_created >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exit_plan_runs_created
    ON exit_plan_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_exit_plan_runs_status
    ON exit_plan_runs (status);

CREATE TABLE IF NOT EXISTS exit_plan_rules (
    id BIGSERIAL PRIMARY KEY,
    exit_plan_id TEXT NOT NULL REFERENCES exit_plans(exit_plan_id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    rule_status TEXT NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exit_plan_rules_plan
    ON exit_plan_rules (exit_plan_id);

CREATE INDEX IF NOT EXISTS idx_exit_plan_rules_type
    ON exit_plan_rules (rule_type);
