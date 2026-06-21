CREATE TABLE IF NOT EXISTS signal_lineage_coverage_analysis (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    lineage_status TEXT NOT NULL CHECK (
        lineage_status IN (
            'COMPLETE',
            'PARTIAL',
            'UNBOUND',
            'DRY_RUN_ONLY',
            'RUNTIME_VERIFIED',
            'MANUAL',
            'ADAPTER',
            'STALE_OR_UNKNOWN',
            'ERROR'
        )
    ),
    lineage_trust_score NUMERIC(10, 6) NOT NULL CHECK (lineage_trust_score >= 0 AND lineage_trust_score <= 1),
    is_bound BOOLEAN NOT NULL DEFAULT FALSE,
    is_unbound BOOLEAN NOT NULL DEFAULT TRUE,
    primary_unbound_reason TEXT NOT NULL CHECK (
        primary_unbound_reason IN (
            'MISSING_PRODUCER',
            'MISSING_SOURCE',
            'MISSING_CORRELATION_ID',
            'MISSING_RAW_PAYLOAD_REF',
            'MISSING_GENERATED_FROM',
            'MISSING_GENERATED_AT',
            'DRY_RUN_ONLY',
            'UNKNOWN_ORIGIN',
            'NO_EVENT_TRACE',
            'NO_PAYLOAD_TRACE',
            'NO_PRODUCER_TRACE',
            'ALREADY_BOUND',
            'UNKNOWN'
        )
    ),
    unbound_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_lineage_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    producer TEXT NULL,
    source TEXT NULL,
    correlation_id TEXT NULL,
    raw_payload_ref TEXT NULL,
    generated_from TEXT NULL,
    generated_by TEXT NULL,
    generated_at TIMESTAMPTZ NULL,
    signal_created_at TIMESTAMPTZ NULL,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_runtime_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_manual_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_adapter_generated BOOLEAN NOT NULL DEFAULT FALSE,
    has_producer BOOLEAN NOT NULL DEFAULT FALSE,
    has_source BOOLEAN NOT NULL DEFAULT FALSE,
    has_correlation_id BOOLEAN NOT NULL DEFAULT FALSE,
    has_raw_payload_ref BOOLEAN NOT NULL DEFAULT FALSE,
    has_generated_from BOOLEAN NOT NULL DEFAULT FALSE,
    has_generated_at BOOLEAN NOT NULL DEFAULT FALSE,
    has_explainable_origin BOOLEAN NOT NULL DEFAULT FALSE,
    can_trace_to_event BOOLEAN NOT NULL DEFAULT FALSE,
    can_trace_to_payload BOOLEAN NOT NULL DEFAULT FALSE,
    can_trace_to_producer BOOLEAN NOT NULL DEFAULT FALSE,
    can_feed_brain_by_lineage BOOLEAN NOT NULL DEFAULT FALSE,
    can_feed_paper_by_lineage BOOLEAN NOT NULL DEFAULT FALSE,
    analysis_status TEXT NOT NULL CHECK (analysis_status IN ('OK', 'PARTIAL', 'ERROR')),
    analysis_error TEXT NULL,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT signal_lineage_coverage_analysis_signal_unique UNIQUE (signal_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_signal
    ON signal_lineage_coverage_analysis (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_status
    ON signal_lineage_coverage_analysis (lineage_status);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_reason
    ON signal_lineage_coverage_analysis (primary_unbound_reason);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_bound
    ON signal_lineage_coverage_analysis (is_bound);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_unbound
    ON signal_lineage_coverage_analysis (is_unbound);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_producer
    ON signal_lineage_coverage_analysis (producer)
    WHERE producer IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_source
    ON signal_lineage_coverage_analysis (source)
    WHERE source IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_correlation
    ON signal_lineage_coverage_analysis (correlation_id)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_dry_run
    ON signal_lineage_coverage_analysis (is_dry_run_generated);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_runtime
    ON signal_lineage_coverage_analysis (is_runtime_generated);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_analysis_status
    ON signal_lineage_coverage_analysis (analysis_status);

CREATE INDEX IF NOT EXISTS idx_signal_lineage_coverage_analyzed
    ON signal_lineage_coverage_analysis (analyzed_at DESC);

CREATE TABLE IF NOT EXISTS signal_lineage_coverage_runs (
    id BIGSERIAL PRIMARY KEY,
    requested_limit INTEGER NOT NULL DEFAULT 0 CHECK (requested_limit >= 0),
    analyzed_count INTEGER NOT NULL DEFAULT 0 CHECK (analyzed_count >= 0),
    bound_count INTEGER NOT NULL DEFAULT 0 CHECK (bound_count >= 0),
    unbound_count INTEGER NOT NULL DEFAULT 0 CHECK (unbound_count >= 0),
    complete_count INTEGER NOT NULL DEFAULT 0 CHECK (complete_count >= 0),
    partial_count INTEGER NOT NULL DEFAULT 0 CHECK (partial_count >= 0),
    dry_run_only_count INTEGER NOT NULL DEFAULT 0 CHECK (dry_run_only_count >= 0),
    runtime_verified_count INTEGER NOT NULL DEFAULT 0 CHECK (runtime_verified_count >= 0),
    missing_producer_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_producer_count >= 0),
    missing_source_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_source_count >= 0),
    missing_correlation_id_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_correlation_id_count >= 0),
    missing_raw_payload_ref_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_raw_payload_ref_count >= 0),
    missing_generated_from_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_generated_from_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('OK', 'PARTIAL', 'ERROR')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL
);
