CREATE TABLE IF NOT EXISTS proactive_seed_mesh_inquiries (
    id BIGSERIAL PRIMARY KEY,
    seed_mesh_inquiry_id TEXT NOT NULL UNIQUE,
    mesh_inquiry_run_id TEXT,
    proactive_candidate_seed_id TEXT NOT NULL,
    source_event_id TEXT,
    event_to_market_link_id TEXT,
    targeted_revalidation_id TEXT,
    market_memory_id TEXT,
    research_watchlist_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    side TEXT NOT NULL,
    token_id TEXT,
    priority_band TEXT,
    priority_score NUMERIC NOT NULL DEFAULT 0,
    request_state TEXT NOT NULL DEFAULT 'PENDING',
    mesh_handoff_mode TEXT NOT NULL DEFAULT 'DATA_ONLY',
    research_only BOOLEAN NOT NULL DEFAULT TRUE,
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    mesh_inquiry_session_id TEXT,
    edge_result_id TEXT,
    trade_thesis_id TEXT,
    opportunity_score_id TEXT,
    risk_evidence_id TEXT,
    capital_evidence_id TEXT,
    exit_evidence_id TEXT,
    lifecycle_evidence_id TEXT,
    blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_inquiries_seed
    ON proactive_seed_mesh_inquiries (proactive_candidate_seed_id);
CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_inquiries_market
    ON proactive_seed_mesh_inquiries (market_id);
CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_inquiries_event
    ON proactive_seed_mesh_inquiries (source_event_id);
CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_inquiries_state
    ON proactive_seed_mesh_inquiries (request_state);

CREATE TABLE IF NOT EXISTS proactive_seed_mesh_results (
    id BIGSERIAL PRIMARY KEY,
    seed_mesh_result_id TEXT NOT NULL UNIQUE,
    seed_mesh_inquiry_id TEXT NOT NULL,
    proactive_candidate_seed_id TEXT NOT NULL,
    result_state TEXT NOT NULL DEFAULT 'SKIPPED',
    edge_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    trade_thesis_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    opportunity_score NUMERIC,
    opportunity_decision_band TEXT NOT NULL DEFAULT 'UNKNOWN',
    risk_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    capital_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    exit_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    lifecycle_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    paper_observation_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    full_paper_ready BOOLEAN NOT NULL DEFAULT FALSE,
    hard_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    soft_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_to_improve_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    mesh_summary TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_results_inquiry
    ON proactive_seed_mesh_results (seed_mesh_inquiry_id);
CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_results_seed
    ON proactive_seed_mesh_results (proactive_candidate_seed_id);
CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_results_state
    ON proactive_seed_mesh_results (result_state);

CREATE TABLE IF NOT EXISTS proactive_seed_mesh_inquiry_runs (
    id BIGSERIAL PRIMARY KEY,
    mesh_inquiry_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    seeds_available INTEGER NOT NULL DEFAULT 0,
    seeds_selected INTEGER NOT NULL DEFAULT 0,
    requests_created INTEGER NOT NULL DEFAULT 0,
    requests_skipped INTEGER NOT NULL DEFAULT 0,
    requests_blocked INTEGER NOT NULL DEFAULT 0,
    requests_failed INTEGER NOT NULL DEFAULT 0,
    results_created INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
