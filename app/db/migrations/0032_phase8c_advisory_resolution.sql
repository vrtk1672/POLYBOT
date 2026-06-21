CREATE TABLE IF NOT EXISTS advisory_resolution_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    advisory_resolution_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_advisory_resolution_runs_started_at
    ON advisory_resolution_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS advisory_resolution_records (
    id UUID PRIMARY KEY,
    advisory_resolution_run_id UUID NOT NULL REFERENCES advisory_resolution_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    invalidation_policy_record_id UUID NULL REFERENCES invalidation_policy_records(id) ON DELETE SET NULL,
    exit_advisory_run_id UUID NULL REFERENCES exit_advisory_runs(id) ON DELETE SET NULL,
    primary_advisory_action_class TEXT NOT NULL CHECK (
        primary_advisory_action_class IN (
            'KEEP',
            'WATCH',
            'REDUCE',
            'PREPARE_EXIT',
            'EXIT',
            'CANCEL_PENDING',
            'BLOCK_NEW_ENTRY',
            'MIXED_ACTIONS',
            'NO_ACTION'
        )
    ),
    primary_priority_class TEXT NOT NULL CHECK (
        primary_priority_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    ),
    action_readiness_class TEXT NOT NULL CHECK (
        action_readiness_class IN (
            'NOT_READY',
            'READY_FOR_REVIEW',
            'READY_FOR_CONTROLLED_ORCHESTRATION'
        )
    ),
    conflict_status_class TEXT NOT NULL CHECK (
        conflict_status_class IN ('NONE', 'MINOR_CONFLICT', 'MATERIAL_CONFLICT')
    ),
    exposure_count INTEGER NOT NULL DEFAULT 0,
    critical_exposure_count INTEGER NOT NULL DEFAULT 0,
    advisory_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    advisory_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    advisory_resolution_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_advisory_resolution_records_run_id
    ON advisory_resolution_records (advisory_resolution_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_advisory_resolution_records_market
    ON advisory_resolution_records (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_advisory_resolution_records_readiness
    ON advisory_resolution_records (action_readiness_class, primary_priority_class, created_at DESC);
