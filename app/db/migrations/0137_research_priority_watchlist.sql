CREATE TABLE IF NOT EXISTS research_priority_watchlist (
    id BIGSERIAL PRIMARY KEY,
    research_watchlist_id TEXT NOT NULL UNIQUE,
    priority_run_id TEXT,
    market_memory_id TEXT NOT NULL,
    market_id TEXT,
    condition_id TEXT,
    priority_band TEXT NOT NULL DEFAULT 'LOW',
    priority_score NUMERIC NOT NULL DEFAULT 0,
    refresh_cadence_seconds INTEGER NOT NULL DEFAULT 3600,
    next_refresh_due_at TIMESTAMPTZ,
    last_refresh_requested_at TIMESTAMPTZ,
    last_refresh_completed_at TIMESTAMPTZ,
    market_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
    token_verification_state TEXT NOT NULL DEFAULT 'TOKENS_MISSING',
    recent_direct_event_count INTEGER NOT NULL DEFAULT 0,
    recent_likely_event_count INTEGER NOT NULL DEFAULT 0,
    recent_revalidation_count INTEGER NOT NULL DEFAULT 0,
    recent_candidate_seed_count INTEGER NOT NULL DEFAULT 0,
    recent_yes_seed_count INTEGER NOT NULL DEFAULT 0,
    recent_no_seed_count INTEGER NOT NULL DEFAULT 0,
    best_opportunity_score NUMERIC,
    paper_observation_interest_count INTEGER NOT NULL DEFAULT 0,
    full_paper_ready_count INTEGER NOT NULL DEFAULT 0,
    liquidity_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    spread_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    volume_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    movement_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    payout_odds_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    time_to_close_seconds INTEGER,
    closing_soon BOOLEAN NOT NULL DEFAULT FALSE,
    priority_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    demotion_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_to_upgrade_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_inputs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    scheduler_state TEXT NOT NULL DEFAULT 'NOT_DUE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT research_priority_watchlist_band_check
        CHECK (priority_band IN ('HIGH','MEDIUM','LOW','DORMANT','ARCHIVED','PRIORITY_UNKNOWN')),
    CONSTRAINT research_priority_watchlist_scheduler_check
        CHECK (scheduler_state IN ('DUE','NOT_DUE','PAUSED','ARCHIVED','ERROR')),
    CONSTRAINT research_priority_watchlist_score_check
        CHECK (priority_score >= 0 AND priority_score <= 100)
);

CREATE INDEX IF NOT EXISTS idx_research_priority_watchlist_market
    ON research_priority_watchlist (market_id);

CREATE INDEX IF NOT EXISTS idx_research_priority_watchlist_band_due
    ON research_priority_watchlist (priority_band, next_refresh_due_at);

CREATE INDEX IF NOT EXISTS idx_research_priority_watchlist_scheduler
    ON research_priority_watchlist (scheduler_state, next_refresh_due_at);

CREATE TABLE IF NOT EXISTS research_priority_watchlist_runs (
    id BIGSERIAL PRIMARY KEY,
    priority_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    markets_seen INTEGER NOT NULL DEFAULT 0,
    markets_updated INTEGER NOT NULL DEFAULT 0,
    high_count INTEGER NOT NULL DEFAULT 0,
    medium_count INTEGER NOT NULL DEFAULT 0,
    low_count INTEGER NOT NULL DEFAULT 0,
    dormant_count INTEGER NOT NULL DEFAULT 0,
    archived_count INTEGER NOT NULL DEFAULT 0,
    due_now_count INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_research_priority_watchlist_runs_completed
    ON research_priority_watchlist_runs (completed_at DESC);
