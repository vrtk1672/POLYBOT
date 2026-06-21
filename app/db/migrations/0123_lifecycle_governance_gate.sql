CREATE TABLE IF NOT EXISTS lifecycle_governance_decisions (
    id BIGSERIAL PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('FRESH_SEED','PAPER_CANDIDATE','PAPER_INTENT','PAPER_POSITION')),
    subject_id TEXT NOT NULL,
    lifecycle_plan_id TEXT NULL REFERENCES trade_lifecycle_plans(plan_id) ON DELETE SET NULL,
    market_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    actionability_class TEXT NOT NULL CHECK (actionability_class IN (
        'HARD_BLOCK',
        'NO_TRADE',
        'WATCH_FOR_CONFIRMATION',
        'ACTIONABLE_SMALL_PAPER',
        'ACTIONABLE_STANDARD_PAPER',
        'COMPLETE_HIGH_CONFIDENCE'
    )),
    allow_paper_intent BOOLEAN NOT NULL DEFAULT false,
    allow_paper_execution BOOLEAN NOT NULL DEFAULT false,
    critical_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_missing_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_dependent_missing_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    mesh_contributions_count INTEGER NOT NULL DEFAULT 0 CHECK (mesh_contributions_count >= 0),
    coordinator_decision_id TEXT NULL,
    same_market_guard_status TEXT NULL,
    capital_status TEXT NULL,
    risk_status TEXT NULL,
    exit_status TEXT NULL,
    reason TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lifecycle_governance_sources (
    id BIGSERIAL PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES lifecycle_governance_decisions(decision_id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (decision_id, source_table, source_record_id, source_type)
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_governance_subject_created
    ON lifecycle_governance_decisions (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lifecycle_governance_plan_created
    ON lifecycle_governance_decisions (lifecycle_plan_id, created_at DESC)
    WHERE lifecycle_plan_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_lifecycle_governance_actionability_created
    ON lifecycle_governance_decisions (actionability_class, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lifecycle_governance_market_created
    ON lifecycle_governance_decisions (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;
