CREATE TABLE IF NOT EXISTS paper_observation_policy_reviews (
    id BIGSERIAL PRIMARY KEY,
    paper_observation_policy_review_id TEXT NOT NULL UNIQUE,
    review_run_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_MESH',
    proactive_candidate_seed_id TEXT,
    seed_mesh_inquiry_id TEXT,
    adapter_payload_id TEXT,
    opportunity_score_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    side TEXT,
    token_id TEXT,
    observation_policy_state TEXT NOT NULL,
    decision_band TEXT NOT NULL DEFAULT 'PAPER_OBSERVATION',
    opportunity_score NUMERIC NOT NULL DEFAULT 0,
    edge_state TEXT,
    thesis_state TEXT,
    risk_state TEXT,
    capital_state TEXT,
    exit_state TEXT,
    lifecycle_state TEXT,
    orderbook_state TEXT,
    token_verification_state TEXT,
    candidate_event_scope_state TEXT,
    lineage_state TEXT NOT NULL DEFAULT 'MISSING',
    observation_allowed_by_policy BOOLEAN NOT NULL DEFAULT FALSE,
    data_only BOOLEAN NOT NULL DEFAULT TRUE,
    observation_policy_review_only BOOLEAN NOT NULL DEFAULT TRUE,
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    max_observation_notional NUMERIC NOT NULL DEFAULT 0,
    max_open_positions INTEGER NOT NULL DEFAULT 0,
    max_observations_per_market INTEGER NOT NULL DEFAULT 1,
    max_observations_per_trigger_family INTEGER NOT NULL DEFAULT 1,
    max_daily_observation_entries INTEGER NOT NULL DEFAULT 1,
    time_stop_seconds INTEGER,
    exit_required BOOLEAN NOT NULL DEFAULT TRUE,
    invalidation_required BOOLEAN NOT NULL DEFAULT TRUE,
    hard_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    soft_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    limits_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_observation_policy_reviews_seed
    ON paper_observation_policy_reviews (proactive_candidate_seed_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_observation_policy_reviews_market
    ON paper_observation_policy_reviews (market_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_observation_policy_reviews_state
    ON paper_observation_policy_reviews (observation_policy_state, updated_at DESC);

CREATE TABLE IF NOT EXISTS paper_observation_policy_review_runs (
    id BIGSERIAL PRIMARY KEY,
    review_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    classifications_reviewed INTEGER NOT NULL DEFAULT 0,
    eligible_count INTEGER NOT NULL DEFAULT 0,
    watch_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    incomplete_count INTEGER NOT NULL DEFAULT 0,
    full_paper_ready_count INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
