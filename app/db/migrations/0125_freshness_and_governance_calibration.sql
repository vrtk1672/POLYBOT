CREATE TABLE IF NOT EXISTS freshness_governance_checks (
    id BIGSERIAL PRIMARY KEY,
    check_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NULL,
    freshness_status TEXT NOT NULL CHECK (freshness_status IN (
        'FRESH',
        'STALE',
        'EXPIRED',
        'HISTORICAL_ONLY',
        'REFRESH_REQUIRED',
        'UNKNOWN_FRESHNESS'
    )),
    age_seconds INTEGER NULL,
    ttl_seconds INTEGER NULL,
    decision_impact TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS governance_blocker_calibration_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    blockers_analyzed INTEGER NOT NULL DEFAULT 0,
    stale_artifacts INTEGER NOT NULL DEFAULT 0,
    overblocking_count INTEGER NOT NULL DEFAULT 0,
    valid_critical_blockers INTEGER NOT NULL DEFAULT 0,
    optional_misclassified INTEGER NOT NULL DEFAULT 0,
    fixes_applied_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'STARTED',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS governance_blocker_calibration_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES governance_blocker_calibration_runs(run_id) ON DELETE CASCADE,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    blocker TEXT NOT NULL,
    current_classification TEXT NOT NULL,
    recommended_classification TEXT NOT NULL,
    applied_change TEXT NOT NULL DEFAULT 'NONE',
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_freshness_governance_subject_created
    ON freshness_governance_checks (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_freshness_governance_status_created
    ON freshness_governance_checks (freshness_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_freshness_governance_source_created
    ON freshness_governance_checks (source_type, source_id, created_at DESC)
    WHERE source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_governance_calibration_trace_run
    ON governance_blocker_calibration_traces (run_id, created_at DESC);
