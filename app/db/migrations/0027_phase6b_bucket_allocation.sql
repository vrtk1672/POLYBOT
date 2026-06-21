CREATE TABLE IF NOT EXISTS bucket_allocation_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    allocator_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bucket_allocation_runs_started_at
    ON bucket_allocation_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS bucket_allocations (
    id UUID PRIMARY KEY,
    bucket_allocation_run_id UUID NOT NULL REFERENCES bucket_allocation_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    trade_classification_id UUID NOT NULL REFERENCES trade_classifications(id) ON DELETE CASCADE,
    primary_trade_type TEXT NOT NULL CHECK (
        primary_trade_type IN (
            'FAST_TRADE', 'RISKY_HIGHER_UPSIDE', 'WHALE_FOLLOW',
            'SLOW_CONVICTION', 'NO_TRADE'
        )
    ),
    assigned_bucket_class TEXT NOT NULL CHECK (
        assigned_bucket_class IN (
            'FAST_BUCKET', 'RISKY_BUCKET', 'WHALE_BUCKET',
            'CONVICTION_BUCKET', 'RESERVE_BUCKET', 'NO_BUCKET'
        )
    ),
    bucket_target_fraction NUMERIC(6, 5) NOT NULL,
    bucket_cap_fraction NUMERIC(6, 5) NOT NULL,
    deployment_fraction NUMERIC(6, 5) NOT NULL,
    occupancy_status TEXT NOT NULL CHECK (
        occupancy_status IN ('EMPTY', 'AVAILABLE', 'LIMITED', 'SATURATED', 'BLOCKED')
    ),
    deployability_class TEXT NOT NULL CHECK (
        deployability_class IN ('DEPLOYABLE', 'LIMITED', 'SATURATED', 'BLOCKED')
    ),
    allocation_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    allocation_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    allocator_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bucket_allocations_run_id
    ON bucket_allocations (bucket_allocation_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bucket_allocations_market
    ON bucket_allocations (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bucket_allocations_bucket
    ON bucket_allocations (assigned_bucket_class, deployment_fraction DESC, created_at DESC);
