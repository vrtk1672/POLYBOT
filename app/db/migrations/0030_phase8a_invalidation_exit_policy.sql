CREATE TABLE IF NOT EXISTS invalidation_policy_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    policy_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invalidation_policy_runs_started_at
    ON invalidation_policy_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS invalidation_policy_records (
    id UUID PRIMARY KEY,
    invalidation_policy_run_id UUID NOT NULL REFERENCES invalidation_policy_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    cycle_id UUID NULL,
    ranking_policy_candidate_id UUID NULL REFERENCES ranking_policy_candidates(id) ON DELETE SET NULL,
    cognition_summary_id UUID NULL REFERENCES cognition_summaries(id) ON DELETE SET NULL,
    invalidation_reasoning_id UUID NULL REFERENCES invalidation_reasonings(id) ON DELETE SET NULL,
    trade_classification_id UUID NULL REFERENCES trade_classifications(id) ON DELETE SET NULL,
    bucket_allocation_id UUID NULL REFERENCES bucket_allocations(id) ON DELETE SET NULL,
    invalidation_state_class TEXT NOT NULL CHECK (
        invalidation_state_class IN (
            'THESIS_INTACT',
            'WATCH',
            'DEGRADED',
            'INVALIDATION_CANDIDATE',
            'INVALIDATED'
        )
    ),
    exit_policy_class TEXT NOT NULL CHECK (
        exit_policy_class IN (
            'HOLD',
            'MONITOR_CLOSELY',
            'REDUCE_EXPOSURE',
            'PREPARE_EXIT',
            'EXIT_RECOMMENDED',
            'BLOCK_NEW_DEPLOYMENT'
        )
    ),
    invalidation_severity_score NUMERIC(7, 4) NOT NULL,
    exit_urgency_score NUMERIC(7, 4) NOT NULL,
    deployment_gate_effect TEXT NOT NULL CHECK (
        deployment_gate_effect IN ('NONE', 'SOFT_BLOCK', 'HARD_BLOCK')
    ),
    policy_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invalidation_policy_records_run_id
    ON invalidation_policy_records (invalidation_policy_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_invalidation_policy_records_market
    ON invalidation_policy_records (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_invalidation_policy_records_exit_policy
    ON invalidation_policy_records (exit_policy_class, deployment_gate_effect, created_at DESC);
