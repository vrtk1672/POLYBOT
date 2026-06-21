CREATE TABLE IF NOT EXISTS cognition_handoff_runs (
    id UUID PRIMARY KEY,
    external_event_enrichment_run_id UUID NULL REFERENCES external_event_enrichment_runs(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    handoff_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    sent_count INTEGER NOT NULL DEFAULT 0,
    held_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cognition_handoff_runs_started_at
    ON cognition_handoff_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_cognition_handoff_runs_enrichment_run_id
    ON cognition_handoff_runs (external_event_enrichment_run_id)
    WHERE external_event_enrichment_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS cognition_handoff_candidates (
    id UUID PRIMARY KEY,
    cognition_handoff_run_id UUID NOT NULL REFERENCES cognition_handoff_runs(id) ON DELETE CASCADE,
    external_event_id UUID NOT NULL REFERENCES external_events_normalized(id) ON DELETE CASCADE,
    external_event_enrichment_id UUID NOT NULL REFERENCES external_event_enrichments(id) ON DELETE CASCADE,
    intelligence_source_id UUID NOT NULL REFERENCES intelligence_sources(id) ON DELETE CASCADE,
    handoff_decision_class TEXT NULL CHECK (
        handoff_decision_class IN (
            'SEND_TO_INTERPRETER', 'HOLD_FOR_REVIEW', 'SKIP_LOW_SIGNAL', 'SKIP_DUPLICATE', 'SKIP_STALE'
        )
    ),
    handoff_priority_class TEXT NULL CHECK (
        handoff_priority_class IN ('HIGH', 'NORMAL', 'LOW')
    ),
    handoff_reason_code TEXT NULL,
    handoff_reason_text TEXT NULL,
    topic_class TEXT NULL,
    usability_hint_class TEXT NULL,
    novelty_hint_class TEXT NULL,
    contradiction_hint_class TEXT NULL,
    trust_weight_snapshot NUMERIC(6, 5) NOT NULL,
    handoff_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    linked_interpretation_run_id UUID NULL REFERENCES event_interpretation_runs(id) ON DELETE SET NULL,
    linked_interpretation_id UUID NULL REFERENCES event_interpretations(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (
        status IN ('SUCCESS', 'HANDOFF_ERROR')
    ),
    error_text TEXT NULL,
    handoff_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cognition_handoff_candidates_run_id
    ON cognition_handoff_candidates (cognition_handoff_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cognition_handoff_candidates_external_event_id
    ON cognition_handoff_candidates (external_event_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cognition_handoff_candidates_decision
    ON cognition_handoff_candidates (handoff_decision_class, created_at DESC);
