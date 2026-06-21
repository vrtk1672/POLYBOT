CREATE TABLE IF NOT EXISTS paper_eligibility_candidates (
    id BIGSERIAL PRIMARY KEY,
    eligibility_id TEXT NOT NULL UNIQUE,
    thesis_id TEXT NULL,
    risk_decision_id TEXT NULL,
    exit_plan_id TEXT NULL,
    coordinator_decision_id TEXT NULL,
    brain_output_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    signal_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    market_id TEXT NULL,
    side TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ELIGIBLE', 'INELIGIBLE', 'BLOCKED', 'INCOMPLETE', 'ERROR')),
    eligibility_score NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (eligibility_score >= 0 AND eligibility_score <= 1),
    eligibility_blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    orderbook_snapshot_id BIGINT NULL,
    link_confidence NUMERIC(10, 6) NULL CHECK (link_confidence IS NULL OR (link_confidence >= 0 AND link_confidence <= 1)),
    lineage_trusted BOOLEAN NOT NULL DEFAULT false,
    risk_approved BOOLEAN NOT NULL DEFAULT false,
    exit_ready BOOLEAN NOT NULL DEFAULT false,
    not_dry_run BOOLEAN NOT NULL DEFAULT false,
    paper_intent_allowed BOOLEAN NOT NULL DEFAULT false CHECK (paper_intent_allowed = false),
    execution_allowed BOOLEAN NOT NULL DEFAULT false CHECK (execution_allowed = false),
    generated_by TEXT NOT NULL DEFAULT 'runtime',
    producer_name TEXT NOT NULL DEFAULT 'paper_eligibility_gate',
    is_runtime_generated BOOLEAN NOT NULL DEFAULT true,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_candidates_status
    ON paper_eligibility_candidates (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_candidates_market
    ON paper_eligibility_candidates (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_candidates_exit_plan
    ON paper_eligibility_candidates (exit_plan_id)
    WHERE exit_plan_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_candidates_risk
    ON paper_eligibility_candidates (risk_decision_id)
    WHERE risk_decision_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_candidates_thesis
    ON paper_eligibility_candidates (thesis_id)
    WHERE thesis_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS paper_eligibility_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    exit_plans_checked INTEGER NOT NULL DEFAULT 0 CHECK (exit_plans_checked >= 0),
    candidates_created INTEGER NOT NULL DEFAULT 0 CHECK (candidates_created >= 0),
    candidates_updated INTEGER NOT NULL DEFAULT 0 CHECK (candidates_updated >= 0),
    eligible_count INTEGER NOT NULL DEFAULT 0 CHECK (eligible_count >= 0),
    ineligible_count INTEGER NOT NULL DEFAULT 0 CHECK (ineligible_count >= 0),
    blocked_count INTEGER NOT NULL DEFAULT 0 CHECK (blocked_count >= 0),
    incomplete_count INTEGER NOT NULL DEFAULT 0 CHECK (incomplete_count >= 0),
    missing_exit_plan_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_exit_plan_count >= 0),
    missing_risk_decision_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_risk_decision_count >= 0),
    missing_thesis_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_thesis_count >= 0),
    missing_market_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_market_count >= 0),
    missing_orderbook_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_orderbook_count >= 0),
    missing_binding_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_binding_count >= 0),
    missing_lineage_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_lineage_count >= 0),
    dry_run_blocked_count INTEGER NOT NULL DEFAULT 0 CHECK (dry_run_blocked_count >= 0),
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

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_runs_created
    ON paper_eligibility_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_runs_status
    ON paper_eligibility_runs (status);
