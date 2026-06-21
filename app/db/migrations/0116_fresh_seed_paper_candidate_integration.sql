CREATE TABLE IF NOT EXISTS fresh_seed_paper_path_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OK', 'BLOCKED', 'DRY_RUN', 'DEGRADED', 'ERROR')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    seeds_checked INTEGER NOT NULL DEFAULT 0 CHECK (seeds_checked >= 0),
    converted_candidates INTEGER NOT NULL DEFAULT 0 CHECK (converted_candidates >= 0),
    thesis_created INTEGER NOT NULL DEFAULT 0 CHECK (thesis_created >= 0),
    risk_created INTEGER NOT NULL DEFAULT 0 CHECK (risk_created >= 0),
    exit_created INTEGER NOT NULL DEFAULT 0 CHECK (exit_created >= 0),
    eligibility_created INTEGER NOT NULL DEFAULT 0 CHECK (eligibility_created >= 0),
    paper_intents_created INTEGER NOT NULL DEFAULT 0 CHECK (paper_intents_created >= 0),
    blockers_by_stage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    paper_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (paper_orders_delta >= 0),
    paper_fills_delta INTEGER NOT NULL DEFAULT 0 CHECK (paper_fills_delta >= 0),
    paper_positions_delta INTEGER NOT NULL DEFAULT 0 CHECK (paper_positions_delta >= 0),
    error_message TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fresh_seed_paper_path_run_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_fresh_seed_paper_path_runs_created
    ON fresh_seed_paper_path_runs (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS fresh_seed_candidate_conversions (
    id BIGSERIAL PRIMARY KEY,
    conversion_id TEXT NOT NULL UNIQUE,
    seed_id TEXT NOT NULL UNIQUE,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    expected_token_id TEXT NULL,
    orderbook_snapshot_id BIGINT NULL,
    trusted_orderbook_link_id TEXT NULL,
    signal_id TEXT NULL,
    brain_output_id TEXT NULL,
    coordinator_decision_id TEXT NULL,
    candidate_id TEXT NULL,
    thesis_id TEXT NULL,
    risk_decision_id TEXT NULL,
    exit_plan_id TEXT NULL,
    eligibility_id TEXT NULL,
    paper_intent_id TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'READY_FOR_CANDIDATE',
            'CANDIDATE_CREATED',
            'THESIS_CREATED',
            'RISK_CREATED',
            'EXIT_CREATED',
            'ELIGIBILITY_CREATED',
            'PAPER_INTENT_CREATED',
            'BLOCKED_RISK',
            'BLOCKED_EXIT',
            'BLOCKED_ELIGIBILITY',
            'BLOCKED_CAPITAL',
            'BLOCKED_DUPLICATE',
            'BLOCKED_ALREADY_EXECUTED',
            'BLOCKED_NO_TRUSTED_ORDERBOOK',
            'BLOCKED_NO_THESIS',
            'BLOCKED_STALE_MARKET',
            'BLOCKED_UNKNOWN'
        )
    ),
    blocker_reason TEXT NULL,
    blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fresh_seed_candidate_conversion_side_check CHECK (side IS NULL OR side IN ('YES', 'NO'))
);

CREATE INDEX IF NOT EXISTS idx_fresh_seed_candidate_conversions_status
    ON fresh_seed_candidate_conversions (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_fresh_seed_candidate_conversions_market
    ON fresh_seed_candidate_conversions (market_id, side)
    WHERE market_id IS NOT NULL;
