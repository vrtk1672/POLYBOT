-- Market Universe Memory foundation.
-- DATA_ONLY market identity, token, freshness, and research-priority projection.
-- This table is not an execution candidate table and must never grant trading authority.

CREATE TABLE IF NOT EXISTS market_universe_memory (
    id BIGSERIAL PRIMARY KEY,
    market_memory_id TEXT NOT NULL UNIQUE,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    clob_market_id TEXT NULL,
    slug TEXT NULL,
    question TEXT NULL,
    title TEXT NULL,
    description TEXT NULL,
    status TEXT NOT NULL DEFAULT 'UNRESOLVED',
    active BOOLEAN NOT NULL DEFAULT false,
    closed BOOLEAN NOT NULL DEFAULT false,
    resolved BOOLEAN NOT NULL DEFAULT false,
    category TEXT NULL,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcomes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    yes_token_id TEXT NULL,
    no_token_id TEXT NULL,
    outcome_token_ids_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    volume NUMERIC NULL,
    liquidity NUMERIC NULL,
    spread NUMERIC NULL,
    best_bid_yes NUMERIC NULL,
    best_ask_yes NUMERIC NULL,
    best_bid_no NUMERIC NULL,
    best_ask_no NUMERIC NULL,
    close_time TIMESTAMPTZ NULL,
    resolution_time TIMESTAMPTZ NULL,
    last_seen_at TIMESTAMPTZ NULL,
    last_verified_at TIMESTAMPTZ NULL,
    last_metadata_refresh_at TIMESTAMPTZ NULL,
    last_orderbook_refresh_at TIMESTAMPTZ NULL,
    identity_verification_state TEXT NOT NULL DEFAULT 'UNRESOLVED',
    token_verification_state TEXT NOT NULL DEFAULT 'TOKENS_MISSING',
    freshness_state TEXT NOT NULL DEFAULT 'NEEDS_REFRESH',
    research_priority TEXT NOT NULL DEFAULT 'LOW',
    source TEXT NOT NULL DEFAULT 'existing_connector',
    source_payload_hash TEXT NULL,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT market_universe_memory_data_only_status_check
        CHECK (status IN ('ACTIVE','CLOSED','RESOLVED','STALE','UNRESOLVED','ARCHIVED')),
    CONSTRAINT market_universe_memory_identity_state_check
        CHECK (identity_verification_state IN ('VERIFIED','PARTIAL','UNRESOLVED')),
    CONSTRAINT market_universe_memory_token_state_check
        CHECK (token_verification_state IN ('TOKENS_VERIFIED','TOKENS_PARTIAL','TOKENS_MISSING','TOKENS_MISMATCH')),
    CONSTRAINT market_universe_memory_freshness_check
        CHECK (freshness_state IN ('FRESH','STALE','NEEDS_REFRESH')),
    CONSTRAINT market_universe_memory_research_priority_check
        CHECK (research_priority IN ('HIGH','MEDIUM','LOW','DORMANT','ARCHIVED'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_universe_memory_market_id
    ON market_universe_memory (market_id)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_universe_memory_condition_id
    ON market_universe_memory (condition_id)
    WHERE condition_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_universe_memory_slug
    ON market_universe_memory (slug)
    WHERE slug IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_universe_memory_yes_token
    ON market_universe_memory (yes_token_id)
    WHERE yes_token_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_universe_memory_no_token
    ON market_universe_memory (no_token_id)
    WHERE no_token_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_universe_memory_status_priority
    ON market_universe_memory (status, research_priority, updated_at DESC);

CREATE TABLE IF NOT EXISTS market_universe_refresh_runs (
    id BIGSERIAL PRIMARY KEY,
    refresh_run_id TEXT NOT NULL UNIQUE,
    refresh_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ NULL,
    source TEXT NOT NULL DEFAULT 'existing_connector',
    markets_seen INTEGER NOT NULL DEFAULT 0,
    markets_new INTEGER NOT NULL DEFAULT 0,
    markets_updated INTEGER NOT NULL DEFAULT 0,
    markets_changed INTEGER NOT NULL DEFAULT 0,
    markets_closed INTEGER NOT NULL DEFAULT 0,
    markets_resolved INTEGER NOT NULL DEFAULT 0,
    markets_stale INTEGER NOT NULL DEFAULT 0,
    markets_unresolved INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_universe_refresh_runs_completed
    ON market_universe_refresh_runs (completed_at DESC NULLS LAST, id DESC);
