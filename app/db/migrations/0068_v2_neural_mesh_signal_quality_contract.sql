CREATE TABLE IF NOT EXISTS signal_quality_evaluations (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    quality_score NUMERIC(5,4) NOT NULL CHECK (quality_score >= 0 AND quality_score <= 1),
    quality_status TEXT NOT NULL CHECK (
        quality_status IN ('GOOD', 'PARTIAL', 'WEAK', 'STALE', 'UNLINKED', 'UNBOUND', 'DRY_RUN_ONLY', 'BLOCKED', 'ERROR')
    ),
    missing_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    readiness_reason TEXT NULL,
    can_feed_brain BOOLEAN NOT NULL DEFAULT false,
    can_feed_paper BOOLEAN NOT NULL DEFAULT false,
    has_market_id BOOLEAN NOT NULL DEFAULT false,
    has_source BOOLEAN NOT NULL DEFAULT false,
    has_lineage BOOLEAN NOT NULL DEFAULT false,
    has_correlation_id BOOLEAN NOT NULL DEFAULT false,
    has_raw_payload_ref BOOLEAN NOT NULL DEFAULT false,
    has_confidence BOOLEAN NOT NULL DEFAULT false,
    has_strength BOOLEAN NOT NULL DEFAULT false,
    has_freshness BOOLEAN NOT NULL DEFAULT false,
    has_evidence BOOLEAN NOT NULL DEFAULT false,
    linked_to_market BOOLEAN NOT NULL DEFAULT false,
    linked_to_position BOOLEAN NOT NULL DEFAULT false,
    used_by_brain_output BOOLEAN NOT NULL DEFAULT false,
    used_by_coordinator BOOLEAN NOT NULL DEFAULT false,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT false,
    is_runtime_generated BOOLEAN NOT NULL DEFAULT false,
    is_stale BOOLEAN NOT NULL DEFAULT false,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NULL,
    CONSTRAINT signal_quality_evaluations_signal_unique UNIQUE (signal_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_signal_id
    ON signal_quality_evaluations (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_status
    ON signal_quality_evaluations (quality_status);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_score
    ON signal_quality_evaluations (quality_score);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_can_feed_brain
    ON signal_quality_evaluations (can_feed_brain);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_can_feed_paper
    ON signal_quality_evaluations (can_feed_paper);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_evaluated_at
    ON signal_quality_evaluations (evaluated_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_dry_run
    ON signal_quality_evaluations (is_dry_run_generated);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_runtime
    ON signal_quality_evaluations (is_runtime_generated);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_linked_market
    ON signal_quality_evaluations (linked_to_market);

CREATE INDEX IF NOT EXISTS idx_signal_quality_evaluations_has_lineage
    ON signal_quality_evaluations (has_lineage);
