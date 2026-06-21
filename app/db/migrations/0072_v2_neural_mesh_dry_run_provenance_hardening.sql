CREATE TABLE IF NOT EXISTS dry_run_provenance_analysis (
    id BIGSERIAL PRIMARY KEY,
    object_type TEXT NOT NULL CHECK (
        object_type IN (
            'SIGNAL',
            'BRAIN_OUTPUT',
            'COORDINATOR_DECISION',
            'QUALITY_EVALUATION',
            'PROCESSING_STATE',
            'LINK_COVERAGE',
            'LINEAGE_COVERAGE'
        )
    ),
    object_id TEXT NOT NULL CHECK (length(trim(object_id)) > 0),
    generated_by TEXT NOT NULL CHECK (generated_by IN ('dry_run', 'runtime', 'adapter', 'manual', 'unknown')),
    dry_run_id TEXT NULL,
    producer_name TEXT NULL,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_runtime_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_adapter_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_manual_generated BOOLEAN NOT NULL DEFAULT FALSE,
    provenance_status TEXT NOT NULL CHECK (
        provenance_status IN (
            'RUNTIME_VERIFIED',
            'DRY_RUN_ONLY',
            'ADAPTER_GENERATED',
            'MANUAL_GENERATED',
            'UNKNOWN',
            'MIXED',
            'ERROR'
        )
    ),
    provenance_confidence NUMERIC(10, 6) NOT NULL CHECK (provenance_confidence >= 0 AND provenance_confidence <= 1),
    provenance_reason TEXT NULL,
    can_feed_brain_by_provenance BOOLEAN NOT NULL DEFAULT FALSE,
    can_feed_paper_by_provenance BOOLEAN NOT NULL DEFAULT FALSE,
    source_table TEXT NULL,
    source_created_at TIMESTAMPTZ NULL,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT dry_run_provenance_analysis_object_unique UNIQUE (object_type, object_id)
);

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_object
    ON dry_run_provenance_analysis (object_type, object_id);

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_generated_by
    ON dry_run_provenance_analysis (generated_by);

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_dry_run_id
    ON dry_run_provenance_analysis (dry_run_id)
    WHERE dry_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_producer
    ON dry_run_provenance_analysis (producer_name)
    WHERE producer_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_status
    ON dry_run_provenance_analysis (provenance_status);

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_is_dry_run
    ON dry_run_provenance_analysis (is_dry_run_generated);

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_is_runtime
    ON dry_run_provenance_analysis (is_runtime_generated);

CREATE INDEX IF NOT EXISTS idx_dry_run_provenance_analyzed
    ON dry_run_provenance_analysis (analyzed_at DESC);

CREATE TABLE IF NOT EXISTS dry_run_provenance_runs (
    id BIGSERIAL PRIMARY KEY,
    requested_limit INTEGER NOT NULL DEFAULT 0 CHECK (requested_limit >= 0),
    analyzed_count INTEGER NOT NULL DEFAULT 0 CHECK (analyzed_count >= 0),
    brain_outputs_total INTEGER NOT NULL DEFAULT 0 CHECK (brain_outputs_total >= 0),
    brain_outputs_runtime INTEGER NOT NULL DEFAULT 0 CHECK (brain_outputs_runtime >= 0),
    brain_outputs_dry_run INTEGER NOT NULL DEFAULT 0 CHECK (brain_outputs_dry_run >= 0),
    coordinator_decisions_total INTEGER NOT NULL DEFAULT 0 CHECK (coordinator_decisions_total >= 0),
    coordinator_decisions_runtime INTEGER NOT NULL DEFAULT 0 CHECK (coordinator_decisions_runtime >= 0),
    coordinator_decisions_dry_run INTEGER NOT NULL DEFAULT 0 CHECK (coordinator_decisions_dry_run >= 0),
    signals_total INTEGER NOT NULL DEFAULT 0 CHECK (signals_total >= 0),
    signals_runtime INTEGER NOT NULL DEFAULT 0 CHECK (signals_runtime >= 0),
    signals_dry_run INTEGER NOT NULL DEFAULT 0 CHECK (signals_dry_run >= 0),
    unknown_count INTEGER NOT NULL DEFAULT 0 CHECK (unknown_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('OK', 'PARTIAL', 'ERROR')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL
);
