CREATE TABLE IF NOT EXISTS whale_profile_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    profiler_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_profile_runs_started_at
    ON whale_profile_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS whale_profiles (
    id UUID PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    whale_profile_run_id UUID NOT NULL REFERENCES whale_profile_runs(id) ON DELETE CASCADE,
    total_events INTEGER NOT NULL,
    entry_count INTEGER NOT NULL,
    exit_count INTEGER NOT NULL,
    reversal_candidate_count INTEGER NOT NULL,
    unknown_count INTEGER NOT NULL,
    average_size NUMERIC(18, 6) NOT NULL,
    average_notional NUMERIC(18, 6) NULL,
    largest_size NUMERIC(18, 6) NOT NULL,
    largest_notional NUMERIC(18, 6) NULL,
    active_markets_count INTEGER NOT NULL,
    market_specialties_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    timing_consistency_score NUMERIC(6, 5) NOT NULL,
    noise_score NUMERIC(6, 5) NOT NULL,
    average_hold_time NUMERIC(18, 6) NULL,
    follow_value_baseline NUMERIC(6, 5) NOT NULL,
    profile_status TEXT NOT NULL CHECK (
        profile_status IN ('PROFILE_READY', 'SPARSE_HISTORY', 'NOISY', 'REVIEW')
    ),
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    profiler_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_profiles_run_id
    ON whale_profiles (whale_profile_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_whale_profiles_wallet
    ON whale_profiles (wallet_address, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_whale_profiles_follow_value
    ON whale_profiles (follow_value_baseline DESC, created_at DESC);
