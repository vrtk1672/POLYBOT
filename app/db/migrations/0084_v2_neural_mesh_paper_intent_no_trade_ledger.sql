CREATE TABLE IF NOT EXISTS paper_intents (
    id BIGSERIAL PRIMARY KEY,
    paper_intent_id TEXT NOT NULL UNIQUE,
    eligibility_id TEXT NOT NULL UNIQUE,
    thesis_id TEXT NOT NULL,
    risk_decision_id TEXT NOT NULL,
    exit_plan_id TEXT NOT NULL,
    coordinator_decision_id TEXT NULL,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    price_basis TEXT NOT NULL,
    orderbook_snapshot_id BIGINT NULL,
    intended_price NUMERIC(18, 8) NULL,
    max_slippage NUMERIC(18, 8) NULL,
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    intent_status TEXT NOT NULL CHECK (intent_status IN ('CREATED', 'BLOCKED', 'CANCELLED', 'ERROR')),
    intent_type TEXT NOT NULL CHECK (intent_type IN ('PAPER_ENTRY_INTENT', 'PAPER_NO_TRADE_INTENT_PLACEHOLDER')),
    intent_reason TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    paper_only BOOLEAN NOT NULL DEFAULT true,
    live BOOLEAN NOT NULL DEFAULT false,
    execution_allowed BOOLEAN NOT NULL DEFAULT false,
    order_intent_created BOOLEAN NOT NULL DEFAULT false,
    generated_by TEXT NOT NULL DEFAULT 'runtime',
    producer_name TEXT NOT NULL DEFAULT 'paper_intent_gate',
    is_runtime_generated BOOLEAN NOT NULL DEFAULT true,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT paper_intents_paper_only_true CHECK (paper_only = true),
    CONSTRAINT paper_intents_live_false CHECK (live = false),
    CONSTRAINT paper_intents_execution_allowed_false CHECK (execution_allowed = false),
    CONSTRAINT paper_intents_order_intent_created_false CHECK (order_intent_created = false)
);

CREATE INDEX IF NOT EXISTS idx_paper_intents_status
    ON paper_intents (intent_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_intents_market
    ON paper_intents (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_intents_exit
    ON paper_intents (exit_plan_id);

CREATE TABLE IF NOT EXISTS paper_intent_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    candidates_checked INTEGER NOT NULL DEFAULT 0 CHECK (candidates_checked >= 0),
    eligible_candidates INTEGER NOT NULL DEFAULT 0 CHECK (eligible_candidates >= 0),
    paper_intents_created INTEGER NOT NULL DEFAULT 0 CHECK (paper_intents_created >= 0),
    paper_intents_updated INTEGER NOT NULL DEFAULT 0 CHECK (paper_intents_updated >= 0),
    no_trade_records_created INTEGER NOT NULL DEFAULT 0 CHECK (no_trade_records_created >= 0),
    no_trade_records_updated INTEGER NOT NULL DEFAULT 0 CHECK (no_trade_records_updated >= 0),
    blocked_candidates INTEGER NOT NULL DEFAULT 0 CHECK (blocked_candidates >= 0),
    missing_eligibility_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_eligibility_count >= 0),
    accounted_candidates INTEGER NOT NULL DEFAULT 0 CHECK (accounted_candidates >= 0),
    unaccounted_candidates INTEGER NOT NULL DEFAULT 0 CHECK (unaccounted_candidates >= 0),
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

CREATE INDEX IF NOT EXISTS idx_paper_intent_runs_created
    ON paper_intent_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS no_trade_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    candidates_checked INTEGER NOT NULL DEFAULT 0 CHECK (candidates_checked >= 0),
    no_trade_records_created INTEGER NOT NULL DEFAULT 0 CHECK (no_trade_records_created >= 0),
    no_trade_records_updated INTEGER NOT NULL DEFAULT 0 CHECK (no_trade_records_updated >= 0),
    blocked_candidates INTEGER NOT NULL DEFAULT 0 CHECK (blocked_candidates >= 0),
    unaccounted_candidates INTEGER NOT NULL DEFAULT 0 CHECK (unaccounted_candidates >= 0),
    paper_ready_before BOOLEAN NOT NULL DEFAULT false,
    paper_ready_after BOOLEAN NOT NULL DEFAULT false,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_no_trade_runs_created
    ON no_trade_runs (created_at DESC);

ALTER TABLE no_trade_log
    ALTER COLUMN market_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS eligibility_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS thesis_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS risk_decision_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS exit_plan_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS no_trade_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS no_trade_category TEXT NULL,
    ADD COLUMN IF NOT EXISTS blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS missing_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS source_status TEXT NULL,
    ADD COLUMN IF NOT EXISTS generated_by TEXT NOT NULL DEFAULT 'runtime',
    ADD COLUMN IF NOT EXISTS producer_name TEXT NOT NULL DEFAULT 'no_trade_ledger',
    ADD COLUMN IF NOT EXISTS is_runtime_generated BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS is_dry_run_generated BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE no_trade_log
SET no_trade_reason = COALESCE(no_trade_reason, primary_reason),
    no_trade_category = COALESCE(no_trade_category, 'NO_ELIGIBLE_CANDIDATE'),
    source_status = COALESCE(source_status, decision_status),
    updated_at = COALESCE(updated_at, created_at)
WHERE no_trade_reason IS NULL
   OR no_trade_category IS NULL
   OR source_status IS NULL;

ALTER TABLE no_trade_log
    DROP CONSTRAINT IF EXISTS no_trade_log_category_check;

ALTER TABLE no_trade_log
    ADD CONSTRAINT no_trade_log_category_check
        CHECK (
            no_trade_category IS NULL
            OR no_trade_category IN (
                'RISK_BLOCKED',
                'EXIT_BLOCKED',
                'ELIGIBILITY_BLOCKED',
                'MISSING_EVIDENCE',
                'STALE_DATA',
                'WEAK_LINEAGE',
                'DRY_RUN_ONLY',
                'NO_ELIGIBLE_CANDIDATE',
                'ERROR'
            )
        );

CREATE UNIQUE INDEX IF NOT EXISTS uq_no_trade_eligibility
    ON no_trade_log (eligibility_id)
    WHERE eligibility_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_no_trade_log_eligibility
    ON no_trade_log (eligibility_id)
    WHERE eligibility_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_no_trade_log_category
    ON no_trade_log (no_trade_category, created_at DESC)
    WHERE no_trade_category IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_no_trade_log_exit_plan
    ON no_trade_log (exit_plan_id)
    WHERE exit_plan_id IS NOT NULL;
