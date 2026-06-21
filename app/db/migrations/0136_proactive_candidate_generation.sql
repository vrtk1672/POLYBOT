CREATE TABLE IF NOT EXISTS proactive_candidate_seeds (
    id BIGSERIAL PRIMARY KEY,
    proactive_candidate_seed_id TEXT NOT NULL UNIQUE,
    generation_run_id TEXT,
    source_event_id TEXT,
    event_to_market_link_id TEXT,
    targeted_revalidation_id TEXT,
    market_memory_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    side TEXT NOT NULL DEFAULT 'SIDE_UNKNOWN',
    token_id TEXT,
    seed_state TEXT NOT NULL DEFAULT 'GENERATED',
    seed_type TEXT NOT NULL DEFAULT 'EVENT_RECALL_REVALIDATED_MARKET',
    research_only BOOLEAN NOT NULL DEFAULT TRUE,
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    link_type TEXT,
    link_confidence NUMERIC NOT NULL DEFAULT 0,
    direction_for_market TEXT NOT NULL DEFAULT 'UNKNOWN',
    direction_confidence NUMERIC NOT NULL DEFAULT 0,
    orderbook_snapshot_id TEXT,
    orderbook_refresh_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    liquidity_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    spread_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    payout_odds_state TEXT NOT NULL DEFAULT 'MISSING',
    movement_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    already_priced_in_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    candidate_event_scope_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN',
    mesh_handoff_state TEXT NOT NULL DEFAULT 'SKIPPED',
    mesh_inquiry_session_id TEXT,
    blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    soft_warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proactive_candidate_seeds_market_id
    ON proactive_candidate_seeds (market_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_proactive_candidate_seeds_source_event_id
    ON proactive_candidate_seeds (source_event_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_proactive_candidate_seeds_revalidation_id
    ON proactive_candidate_seeds (targeted_revalidation_id, side);

CREATE INDEX IF NOT EXISTS idx_proactive_candidate_seeds_state
    ON proactive_candidate_seeds (seed_state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_proactive_candidate_seeds_research_only
    ON proactive_candidate_seeds (research_only, execution_allowed, paper_allowed, shadow_allowed, live_allowed);

CREATE TABLE IF NOT EXISTS proactive_candidate_generation_runs (
    id BIGSERIAL PRIMARY KEY,
    generation_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    revalidation_rows_seen INTEGER NOT NULL DEFAULT 0,
    seeds_generated INTEGER NOT NULL DEFAULT 0,
    watch_only_seeds INTEGER NOT NULL DEFAULT 0,
    blocked_seeds INTEGER NOT NULL DEFAULT 0,
    duplicate_seeds INTEGER NOT NULL DEFAULT 0,
    mesh_handoff_sent INTEGER NOT NULL DEFAULT 0,
    mesh_handoff_skipped INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
