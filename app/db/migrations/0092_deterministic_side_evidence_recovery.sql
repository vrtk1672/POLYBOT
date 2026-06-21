ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS matched_side TEXT NULL CHECK (matched_side IS NULL OR matched_side IN ('YES', 'NO'));

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS side_source TEXT NULL;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS side_source_id TEXT NULL;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS side_confidence NUMERIC(10, 6) NULL CHECK (side_confidence IS NULL OR (side_confidence >= 0 AND side_confidence <= 1));

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS side_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS side_resolved_at TIMESTAMPTZ NULL;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS side_rejected_reason TEXT NULL;

ALTER TABLE neuron_signal_bindings
    ADD COLUMN IF NOT EXISTS matched_side TEXT NULL CHECK (matched_side IS NULL OR matched_side IN ('YES', 'NO'));

ALTER TABLE neuron_signal_bindings
    ADD COLUMN IF NOT EXISTS side_source TEXT NULL;

ALTER TABLE neuron_signal_bindings
    ADD COLUMN IF NOT EXISTS side_source_id TEXT NULL;

ALTER TABLE neuron_signal_bindings
    ADD COLUMN IF NOT EXISTS side_confidence NUMERIC(10, 6) NULL CHECK (side_confidence IS NULL OR (side_confidence >= 0 AND side_confidence <= 1));

ALTER TABLE neuron_signal_bindings
    ADD COLUMN IF NOT EXISTS side_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE neuron_signal_bindings
    ADD COLUMN IF NOT EXISTS side_resolved_at TIMESTAMPTZ NULL;

ALTER TABLE neuron_signal_bindings
    ADD COLUMN IF NOT EXISTS side_rejected_reason TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_market_links_matched_side
    ON signal_market_links (matched_side)
    WHERE matched_side IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_market_links_side_resolved
    ON signal_market_links (side_resolved_at DESC)
    WHERE side_resolved_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_matched_side
    ON neuron_signal_bindings (matched_side)
    WHERE matched_side IS NOT NULL;

CREATE TABLE IF NOT EXISTS side_evidence_recovery_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    links_checked INTEGER NOT NULL DEFAULT 0 CHECK (links_checked >= 0),
    candidates_checked INTEGER NOT NULL DEFAULT 0 CHECK (candidates_checked >= 0),
    token_mappings_checked INTEGER NOT NULL DEFAULT 0 CHECK (token_mappings_checked >= 0),
    sides_recovered INTEGER NOT NULL DEFAULT 0 CHECK (sides_recovered >= 0),
    sides_rejected INTEGER NOT NULL DEFAULT 0 CHECK (sides_rejected >= 0),
    ambiguous_side_count INTEGER NOT NULL DEFAULT 0 CHECK (ambiguous_side_count >= 0),
    missing_token_mapping_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_token_mapping_count >= 0),
    side_conflict_count INTEGER NOT NULL DEFAULT 0 CHECK (side_conflict_count >= 0),
    candidates_with_side_before INTEGER NOT NULL DEFAULT 0 CHECK (candidates_with_side_before >= 0),
    candidates_with_side_after INTEGER NOT NULL DEFAULT 0 CHECK (candidates_with_side_after >= 0),
    eligible_before INTEGER NOT NULL DEFAULT 0 CHECK (eligible_before >= 0),
    eligible_after INTEGER NOT NULL DEFAULT 0 CHECK (eligible_after >= 0),
    paper_intents_before INTEGER NOT NULL DEFAULT 0 CHECK (paper_intents_before >= 0),
    paper_intents_after INTEGER NOT NULL DEFAULT 0 CHECK (paper_intents_after >= 0),
    paper_positions_delta INTEGER NOT NULL DEFAULT 0 CHECK (paper_positions_delta >= 0),
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    top_rejected_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_side_evidence_runs_created
    ON side_evidence_recovery_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_side_evidence_runs_cycle
    ON side_evidence_recovery_runs (cycle_id)
    WHERE cycle_id IS NOT NULL;
