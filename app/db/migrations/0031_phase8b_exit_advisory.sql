CREATE TABLE IF NOT EXISTS exit_advisory_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    advisory_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exit_advisory_runs_started_at
    ON exit_advisory_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS exit_advisory_records (
    id UUID PRIMARY KEY,
    exit_advisory_run_id UUID NOT NULL REFERENCES exit_advisory_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    invalidation_policy_record_id UUID NOT NULL REFERENCES invalidation_policy_records(id) ON DELETE CASCADE,
    exposure_type TEXT NOT NULL CHECK (
        exposure_type IN (
            'PAPER_POSITION',
            'PAPER_ORDER',
            'SHADOW_POSITION',
            'SHADOW_ORDER',
            'LIVE_POSITION',
            'LIVE_ORDER'
        )
    ),
    exposure_ref_id UUID NOT NULL,
    advisory_action_class TEXT NOT NULL CHECK (
        advisory_action_class IN (
            'KEEP',
            'WATCH',
            'REDUCE',
            'PREPARE_EXIT',
            'EXIT',
            'CANCEL_PENDING',
            'BLOCK_NEW_ENTRY'
        )
    ),
    advisory_priority_class TEXT NOT NULL CHECK (
        advisory_priority_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    ),
    advisory_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    advisory_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    advisory_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exit_advisory_records_run_id
    ON exit_advisory_records (exit_advisory_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_exit_advisory_records_market
    ON exit_advisory_records (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_exit_advisory_records_priority
    ON exit_advisory_records (advisory_priority_class, advisory_action_class, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_exit_advisory_records_exposure
    ON exit_advisory_records (exposure_type, exposure_ref_id, created_at DESC);
