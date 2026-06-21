CREATE TABLE IF NOT EXISTS command_intent_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')),
    command_intent_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_command_intent_runs_started_at
    ON command_intent_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS command_intent_records (
    id UUID PRIMARY KEY,
    command_intent_run_id UUID NOT NULL REFERENCES command_intent_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    advisory_resolution_record_id UUID NOT NULL REFERENCES advisory_resolution_records(id) ON DELETE CASCADE,
    exit_advisory_record_id UUID NULL REFERENCES exit_advisory_records(id) ON DELETE SET NULL,
    exposure_type TEXT NOT NULL,
    exposure_ref_id TEXT NOT NULL,
    command_intent_class TEXT NOT NULL CHECK (
        command_intent_class IN (
            'NO_OP',
            'WATCH_ONLY',
            'REDUCE_POSITION',
            'PREPARE_POSITION_EXIT',
            'EXIT_POSITION',
            'CANCEL_PENDING_ORDER',
            'BLOCK_NEW_ENTRY'
        )
    ),
    command_priority_class TEXT NOT NULL CHECK (command_priority_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    command_status_class TEXT NOT NULL CHECK (command_status_class IN ('STAGED', 'NOT_ELIGIBLE', 'SUPPRESSED')),
    orchestration_eligibility_class TEXT NOT NULL CHECK (
        orchestration_eligibility_class IN (
            'INELIGIBLE',
            'REVIEW_REQUIRED',
            'ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION'
        )
    ),
    command_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    command_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    advisory_resolution_version TEXT NULL,
    command_intent_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_command_intent_records_run_id
    ON command_intent_records (command_intent_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_command_intent_records_market_id
    ON command_intent_records (market_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_command_intent_records_eligibility
    ON command_intent_records (orchestration_eligibility_class, command_priority_class, created_at DESC);
