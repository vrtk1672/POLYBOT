CREATE TABLE IF NOT EXISTS runtime_producer_evidence_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    producer_name TEXT,
    source TEXT,
    status TEXT NOT NULL,
    producers_checked INTEGER NOT NULL DEFAULT 0,
    runtime_producers_active_before INTEGER NOT NULL DEFAULT 0,
    runtime_producers_active_after INTEGER NOT NULL DEFAULT 0,
    dry_run_only_producers_before INTEGER NOT NULL DEFAULT 0,
    dry_run_only_producers_after INTEGER NOT NULL DEFAULT 0,
    signals_created INTEGER NOT NULL DEFAULT 0,
    signals_updated INTEGER NOT NULL DEFAULT 0,
    quality_updated INTEGER NOT NULL DEFAULT 0,
    processing_updated INTEGER NOT NULL DEFAULT 0,
    lineage_updated INTEGER NOT NULL DEFAULT 0,
    link_coverage_updated INTEGER NOT NULL DEFAULT 0,
    provenance_updated INTEGER NOT NULL DEFAULT 0,
    producer_health_updated BOOLEAN NOT NULL DEFAULT FALSE,
    mesh_blockers_updated BOOLEAN NOT NULL DEFAULT FALSE,
    paper_ready_before BOOLEAN NOT NULL DEFAULT FALSE,
    paper_ready_after BOOLEAN NOT NULL DEFAULT FALSE,
    orders_created INTEGER NOT NULL DEFAULT 0,
    order_intents_created INTEGER NOT NULL DEFAULT 0,
    live_actions_created INTEGER NOT NULL DEFAULT 0,
    blocked_by JSONB NOT NULL DEFAULT '[]'::jsonb,
    remaining_blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_summary TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_producer_evidence_status_check
        CHECK (status IN ('OK', 'DEGRADED', 'DRY_RUN', 'ERROR')),
    CONSTRAINT runtime_producer_evidence_no_paper_ready_check
        CHECK (paper_ready_before = FALSE AND paper_ready_after = FALSE),
    CONSTRAINT runtime_producer_evidence_no_execution_check
        CHECK (orders_created = 0 AND order_intents_created = 0 AND live_actions_created = 0)
);

CREATE TABLE IF NOT EXISTS runtime_producer_evidence_items (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runtime_producer_evidence_runs(run_id) ON DELETE CASCADE,
    signal_id TEXT,
    producer_name TEXT NOT NULL,
    source TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    raw_payload_ref TEXT NOT NULL,
    generated_from TEXT NOT NULL,
    generated_by TEXT NOT NULL DEFAULT 'runtime',
    is_runtime_generated BOOLEAN NOT NULL DEFAULT TRUE,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'OK',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_producer_evidence_items_generated_by_check
        CHECK (generated_by = 'runtime'),
    CONSTRAINT runtime_producer_evidence_items_runtime_check
        CHECK (is_runtime_generated = TRUE AND is_dry_run_generated = FALSE),
    CONSTRAINT runtime_producer_evidence_items_status_check
        CHECK (status IN ('OK', 'PLANNED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS idx_runtime_producer_evidence_runs_created_at
    ON runtime_producer_evidence_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_runtime_producer_evidence_runs_status
    ON runtime_producer_evidence_runs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_runtime_producer_evidence_items_run_id
    ON runtime_producer_evidence_items (run_id);

CREATE INDEX IF NOT EXISTS idx_runtime_producer_evidence_items_signal_id
    ON runtime_producer_evidence_items (signal_id);

CREATE INDEX IF NOT EXISTS idx_runtime_producer_evidence_items_producer
    ON runtime_producer_evidence_items (producer_name, created_at DESC);
