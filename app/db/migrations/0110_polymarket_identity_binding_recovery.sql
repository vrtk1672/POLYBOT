CREATE TABLE IF NOT EXISTS polymarket_binding_recovery_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    candidates_checked INTEGER NOT NULL DEFAULT 0 CHECK (candidates_checked >= 0),
    market_ids_backfilled INTEGER NOT NULL DEFAULT 0 CHECK (market_ids_backfilled >= 0),
    sides_backfilled INTEGER NOT NULL DEFAULT 0 CHECK (sides_backfilled >= 0),
    market_identity_backfilled INTEGER NOT NULL DEFAULT 0 CHECK (market_identity_backfilled >= 0),
    expected_tokens_resolved INTEGER NOT NULL DEFAULT 0 CHECK (expected_tokens_resolved >= 0),
    clob_books_attempted INTEGER NOT NULL DEFAULT 0 CHECK (clob_books_attempted >= 0),
    orderbook_snapshots_created INTEGER NOT NULL DEFAULT 0 CHECK (orderbook_snapshots_created >= 0),
    trusted_links_created INTEGER NOT NULL DEFAULT 0 CHECK (trusted_links_created >= 0),
    trusted_links_refreshed INTEGER NOT NULL DEFAULT 0 CHECK (trusted_links_refreshed >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    blocker_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    trace_count INTEGER NOT NULL DEFAULT 0 CHECK (trace_count >= 0),
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT polymarket_binding_run_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_polymarket_binding_runs_created
    ON polymarket_binding_recovery_runs (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_polymarket_binding_runs_cycle
    ON polymarket_binding_recovery_runs (cycle_id);

CREATE TABLE IF NOT EXISTS polymarket_binding_candidate_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    source_signal_id TEXT NULL,
    market_id TEXT NULL,
    slug TEXT NULL,
    question TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    yes_token_id TEXT NULL,
    no_token_id TEXT NULL,
    expected_token_id TEXT NULL,
    current_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    candidate_source TEXT NULL,
    gamma_market_match_found BOOLEAN NOT NULL DEFAULT false,
    clob_token_book_check_attempted BOOLEAN NOT NULL DEFAULT false,
    clob_book_status TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED',
    best_bid NUMERIC NULL,
    best_ask NUMERIC NULL,
    spread NUMERIC NULL,
    snapshot_id BIGINT NULL,
    trust_link_id TEXT NULL,
    exact_fix_category TEXT NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT polymarket_binding_trace_side_check CHECK (side IS NULL OR side IN ('YES', 'NO')),
    CONSTRAINT polymarket_binding_trace_unique UNIQUE (run_id, candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_polymarket_binding_traces_run
    ON polymarket_binding_candidate_traces (run_id, id);

CREATE INDEX IF NOT EXISTS idx_polymarket_binding_traces_category
    ON polymarket_binding_candidate_traces (exact_fix_category, created_at DESC);

