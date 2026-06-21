CREATE TABLE IF NOT EXISTS clob_token_book_verification_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    fresh_verified_candidates INTEGER NOT NULL DEFAULT 0 CHECK (fresh_verified_candidates >= 0),
    stale_market_skipped INTEGER NOT NULL DEFAULT 0 CHECK (stale_market_skipped >= 0),
    fresh_seeds_created INTEGER NOT NULL DEFAULT 0 CHECK (fresh_seeds_created >= 0),
    seed_candidates_checked INTEGER NOT NULL DEFAULT 0 CHECK (seed_candidates_checked >= 0),
    clob_checks_attempted INTEGER NOT NULL DEFAULT 0 CHECK (clob_checks_attempted >= 0),
    clob_books_verified INTEGER NOT NULL DEFAULT 0 CHECK (clob_books_verified >= 0),
    snapshots_created INTEGER NOT NULL DEFAULT 0 CHECK (snapshots_created >= 0),
    trusted_links_created INTEGER NOT NULL DEFAULT 0 CHECK (trusted_links_created >= 0),
    trusted_links_refreshed INTEGER NOT NULL DEFAULT 0 CHECK (trusted_links_refreshed >= 0),
    token_not_found_count INTEGER NOT NULL DEFAULT 0 CHECK (token_not_found_count >= 0),
    clob_no_book_count INTEGER NOT NULL DEFAULT 0 CHECK (clob_no_book_count >= 0),
    asset_id_mismatch_count INTEGER NOT NULL DEFAULT 0 CHECK (asset_id_mismatch_count >= 0),
    condition_id_mismatch_count INTEGER NOT NULL DEFAULT 0 CHECK (condition_id_mismatch_count >= 0),
    empty_bid_ask_count INTEGER NOT NULL DEFAULT 0 CHECK (empty_bid_ask_count >= 0),
    spread_too_wide_count INTEGER NOT NULL DEFAULT 0 CHECK (spread_too_wide_count >= 0),
    liquidity_too_low_count INTEGER NOT NULL DEFAULT 0 CHECK (liquidity_too_low_count >= 0),
    blocker_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT clob_token_book_verification_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_clob_token_book_verification_runs_created
    ON clob_token_book_verification_runs (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS fresh_candidate_seeds (
    id BIGSERIAL PRIMARY KEY,
    seed_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    slug TEXT NULL,
    question TEXT NULL,
    side TEXT NOT NULL,
    expected_token_id TEXT NOT NULL,
    yes_token_id TEXT NOT NULL,
    no_token_id TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    orderbook_snapshot_id BIGINT NULL,
    trusted_link_id TEXT NULL,
    rejection_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fresh_candidate_seed_side_check CHECK (side IN ('YES', 'NO')),
    CONSTRAINT fresh_candidate_seed_status_check CHECK (status IN ('SEEDED', 'BOOK_VERIFIED', 'BOOK_REJECTED', 'NOT_TRADABLE', 'AMBIGUOUS'))
);

CREATE INDEX IF NOT EXISTS idx_fresh_candidate_seeds_market
    ON fresh_candidate_seeds (market_id, side);

CREATE INDEX IF NOT EXISTS idx_fresh_candidate_seeds_status
    ON fresh_candidate_seeds (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS clob_token_book_verification_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    trace_type TEXT NOT NULL,
    candidate_id TEXT NULL,
    seed_id TEXT NULL,
    market_id TEXT NULL,
    slug TEXT NULL,
    question TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    identity_status TEXT NULL,
    expected_token_id TEXT NULL,
    clob_book_attempted BOOLEAN NOT NULL DEFAULT false,
    clob_book_status TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED',
    rejection_reason TEXT NULL,
    asset_id TEXT NULL,
    response_market TEXT NULL,
    best_bid NUMERIC NULL,
    best_ask NUMERIC NULL,
    spread NUMERIC NULL,
    liquidity_score NUMERIC NULL,
    snapshot_id BIGINT NULL,
    trust_link_id TEXT NULL,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT clob_token_book_trace_side_check CHECK (side IS NULL OR side IN ('YES', 'NO'))
);

CREATE INDEX IF NOT EXISTS idx_clob_token_book_traces_run
    ON clob_token_book_verification_traces (run_id, id);

CREATE INDEX IF NOT EXISTS idx_clob_token_book_traces_status
    ON clob_token_book_verification_traces (rejection_reason, created_at DESC);
