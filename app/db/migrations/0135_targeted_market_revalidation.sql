CREATE TABLE IF NOT EXISTS targeted_market_revalidations (
    id BIGSERIAL PRIMARY KEY,
    targeted_revalidation_id TEXT NOT NULL UNIQUE,
    refresh_run_id TEXT,
    source_event_id TEXT NOT NULL,
    event_to_market_link_id TEXT NOT NULL,
    market_memory_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    link_type TEXT NOT NULL,
    link_confidence NUMERIC NOT NULL DEFAULT 0,
    revalidation_state TEXT NOT NULL DEFAULT 'SKIPPED',
    skip_reason TEXT,
    failure_reason TEXT,
    market_identity_state TEXT NOT NULL DEFAULT 'UNRESOLVED',
    token_verification_state TEXT NOT NULL DEFAULT 'TOKENS_MISSING',
    token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN',
    metadata_refresh_state TEXT NOT NULL DEFAULT 'NOT_AVAILABLE',
    orderbook_refresh_state TEXT NOT NULL DEFAULT 'NOT_AVAILABLE',
    selected_orderbook_snapshot_id TEXT,
    liquidity_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    spread_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    payout_odds_state TEXT NOT NULL DEFAULT 'MISSING',
    movement_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    signal_state TEXT NOT NULL DEFAULT 'MISSING',
    candidate_event_scope_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    already_priced_in_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    already_priced_in_reason TEXT,
    eligible_for_candidate_generation_later BOOLEAN NOT NULL DEFAULT FALSE,
    candidate_generation_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_targeted_revalidations_market_id ON targeted_market_revalidations (market_id);
CREATE INDEX IF NOT EXISTS idx_targeted_revalidations_source_event_id ON targeted_market_revalidations (source_event_id);
CREATE INDEX IF NOT EXISTS idx_targeted_revalidations_link_id ON targeted_market_revalidations (event_to_market_link_id);
CREATE INDEX IF NOT EXISTS idx_targeted_revalidations_state ON targeted_market_revalidations (revalidation_state);
CREATE INDEX IF NOT EXISTS idx_targeted_revalidations_candidate_later ON targeted_market_revalidations (eligible_for_candidate_generation_later);
CREATE INDEX IF NOT EXISTS idx_targeted_revalidations_updated_at ON targeted_market_revalidations (updated_at DESC);

CREATE TABLE IF NOT EXISTS targeted_market_revalidation_refresh_runs (
    id BIGSERIAL PRIMARY KEY,
    refresh_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    eligible_links_seen INTEGER NOT NULL DEFAULT 0,
    links_revalidated INTEGER NOT NULL DEFAULT 0,
    links_skipped INTEGER NOT NULL DEFAULT 0,
    links_failed INTEGER NOT NULL DEFAULT 0,
    links_partial INTEGER NOT NULL DEFAULT 0,
    markets_refreshed INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_targeted_revalidation_runs_completed_at ON targeted_market_revalidation_refresh_runs (completed_at DESC);
