CREATE TABLE IF NOT EXISTS fresh_market_identity_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    system_power TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT false,
    candidates_checked INTEGER NOT NULL DEFAULT 0 CHECK (candidates_checked >= 0),
    fresh_verified_count INTEGER NOT NULL DEFAULT 0 CHECK (fresh_verified_count >= 0),
    stale_market_count INTEGER NOT NULL DEFAULT 0 CHECK (stale_market_count >= 0),
    missing_market_id_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_market_id_count >= 0),
    missing_condition_id_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_condition_id_count >= 0),
    missing_side_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_side_count >= 0),
    missing_token_mapping_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_token_mapping_count >= 0),
    accepting_orders_false_count INTEGER NOT NULL DEFAULT 0 CHECK (accepting_orders_false_count >= 0),
    market_closed_count INTEGER NOT NULL DEFAULT 0 CHECK (market_closed_count >= 0),
    ambiguous_count INTEGER NOT NULL DEFAULT 0 CHECK (ambiguous_count >= 0),
    unrecoverable_count INTEGER NOT NULL DEFAULT 0 CHECK (unrecoverable_count >= 0),
    blocker_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fresh_market_identity_run_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_fresh_market_identity_runs_created
    ON fresh_market_identity_runs (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS fresh_market_identity_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    source_signal_id TEXT NULL,
    market_id TEXT NULL,
    slug TEXT NULL,
    question TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    yes_token_id TEXT NULL,
    no_token_id TEXT NULL,
    expected_token_id TEXT NULL,
    market_active BOOLEAN NULL,
    market_closed BOOLEAN NULL,
    accepting_orders BOOLEAN NULL,
    gamma_lookup_attempted BOOLEAN NOT NULL DEFAULT false,
    gamma_lookup_status TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED',
    identity_source TEXT NULL,
    identity_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fresh_market_identity_trace_side_check CHECK (side IS NULL OR side IN ('YES', 'NO')),
    CONSTRAINT fresh_market_identity_trace_unique UNIQUE (run_id, candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_fresh_market_identity_traces_run
    ON fresh_market_identity_traces (run_id, id);

CREATE INDEX IF NOT EXISTS idx_fresh_market_identity_traces_status
    ON fresh_market_identity_traces (identity_status, created_at DESC);

ALTER TABLE paper_eligibility_candidates
    ADD COLUMN IF NOT EXISTS identity_status TEXT NULL,
    ADD COLUMN IF NOT EXISTS identity_verified_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS identity_source TEXT NULL,
    ADD COLUMN IF NOT EXISTS expected_token_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS identity_blocker_reason TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_paper_eligibility_identity_status
    ON paper_eligibility_candidates (identity_status, updated_at DESC);
