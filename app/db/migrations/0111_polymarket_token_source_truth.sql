CREATE TABLE IF NOT EXISTS polymarket_token_truth_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    candidates_checked INTEGER NOT NULL DEFAULT 0,
    gamma_markets_checked INTEGER NOT NULL DEFAULT 0,
    tokens_resolved INTEGER NOT NULL DEFAULT 0,
    clob_checks_attempted INTEGER NOT NULL DEFAULT 0,
    verified_token_books INTEGER NOT NULL DEFAULT 0,
    token_not_found_count INTEGER NOT NULL DEFAULT 0,
    token_parse_error_count INTEGER NOT NULL DEFAULT 0,
    ambiguous_token_count INTEGER NOT NULL DEFAULT 0,
    trusted_links_created INTEGER NOT NULL DEFAULT 0,
    trusted_links_refreshed INTEGER NOT NULL DEFAULT 0,
    orderbook_snapshots_created INTEGER NOT NULL DEFAULT 0,
    blocker_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_orders_delta INTEGER NOT NULL DEFAULT 0,
    real_orders_delta INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT polymarket_token_truth_run_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_polymarket_token_truth_runs_created
    ON polymarket_token_truth_runs (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS polymarket_token_bindings (
    id BIGSERIAL PRIMARY KEY,
    binding_id TEXT NOT NULL UNIQUE,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    slug TEXT NULL,
    question TEXT NULL,
    outcome_label TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    token_source TEXT NULL,
    gamma_field TEXT NULL,
    confidence NUMERIC NULL,
    accepting_orders BOOLEAN NULL,
    closed BOOLEAN NULL,
    active BOOLEAN NULL,
    verified_by_clob_book BOOLEAN NOT NULL DEFAULT false,
    clob_book_status TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT polymarket_token_binding_side_check CHECK (side IS NULL OR side IN ('YES','NO'))
);

CREATE INDEX IF NOT EXISTS idx_polymarket_token_bindings_market
    ON polymarket_token_bindings (market_id, side);

CREATE INDEX IF NOT EXISTS idx_polymarket_token_bindings_token
    ON polymarket_token_bindings (token_id);

CREATE TABLE IF NOT EXISTS polymarket_token_truth_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    trace_type TEXT NOT NULL,
    candidate_id TEXT NULL,
    market_id TEXT NULL,
    slug TEXT NULL,
    question TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    stored_yes_token_id TEXT NULL,
    stored_no_token_id TEXT NULL,
    candidate_token_id TEXT NULL,
    expected_token_id TEXT NULL,
    clob_attempted_token_id TEXT NULL,
    gamma_field TEXT NULL,
    token_source TEXT NULL,
    token_binding_confidence NUMERIC NULL,
    accepting_orders BOOLEAN NULL,
    closed BOOLEAN NULL,
    active BOOLEAN NULL,
    enable_order_book BOOLEAN NULL,
    clob_book_attempted BOOLEAN NOT NULL DEFAULT false,
    clob_book_status TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED',
    clob_error_summary TEXT NULL,
    best_bid NUMERIC NULL,
    best_ask NUMERIC NULL,
    spread NUMERIC NULL,
    snapshot_id BIGINT NULL,
    trust_link_id TEXT NULL,
    classification TEXT NOT NULL,
    exact_fix_category TEXT NOT NULL,
    raw_gamma_fields_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_polymarket_token_truth_traces_run
    ON polymarket_token_truth_traces (run_id, id);

CREATE INDEX IF NOT EXISTS idx_polymarket_token_truth_traces_classification
    ON polymarket_token_truth_traces (classification, created_at DESC);

