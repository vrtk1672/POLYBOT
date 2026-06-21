CREATE TABLE IF NOT EXISTS paper_runtime_decisions (
    id BIGSERIAL PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_MESH',
    candidate_source TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_MESH',
    source_review_id TEXT,
    proactive_candidate_seed_id TEXT,
    seed_mesh_inquiry_id TEXT,
    adapter_payload_id TEXT,
    opportunity_score_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    side TEXT,
    token_id TEXT,
    decision TEXT NOT NULL CHECK (decision IN ('ENTER','WATCH','BLOCK')),
    decision_mode TEXT NOT NULL DEFAULT 'PAPER',
    execution_mode TEXT NOT NULL DEFAULT 'PAPER',
    paper_enter_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    live_enter_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    edge_state TEXT,
    thesis_state TEXT,
    opportunity_score NUMERIC NOT NULL DEFAULT 0,
    risk_state TEXT,
    capital_state TEXT,
    exit_state TEXT,
    lifecycle_state TEXT,
    orderbook_state TEXT,
    orderbook_snapshot_id BIGINT,
    token_verification_state TEXT,
    candidate_event_scope_state TEXT,
    lineage_state TEXT,
    research_lineage JSONB NOT NULL DEFAULT '{}'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_by TEXT NOT NULL DEFAULT 'paper_runtime_decision_service',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_runtime_decisions_mode_decision
    ON paper_runtime_decisions (execution_mode, decision, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_runtime_decisions_market_side
    ON paper_runtime_decisions (market_id, side, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_runtime_decisions_seed
    ON paper_runtime_decisions (proactive_candidate_seed_id, updated_at DESC)
    WHERE proactive_candidate_seed_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS paper_runtime_decision_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    candidates_reviewed INTEGER NOT NULL DEFAULT 0,
    enter_count INTEGER NOT NULL DEFAULT 0,
    watch_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
