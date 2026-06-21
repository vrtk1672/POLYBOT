CREATE TABLE IF NOT EXISTS external_event_enrichment_runs (
    id UUID PRIMARY KEY,
    intelligence_ingestion_run_id UUID NULL REFERENCES intelligence_ingestion_runs(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    enrichment_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_external_event_enrichment_runs_started_at
    ON external_event_enrichment_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_event_enrichment_runs_ingestion_run_id
    ON external_event_enrichment_runs (intelligence_ingestion_run_id)
    WHERE intelligence_ingestion_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS external_event_enrichments (
    id UUID PRIMARY KEY,
    external_event_enrichment_run_id UUID NOT NULL REFERENCES external_event_enrichment_runs(id) ON DELETE CASCADE,
    external_event_id UUID NOT NULL REFERENCES external_events_normalized(id) ON DELETE CASCADE,
    intelligence_source_id UUID NOT NULL REFERENCES intelligence_sources(id) ON DELETE CASCADE,
    normalized_title_snapshot TEXT NOT NULL,
    normalized_summary_snapshot TEXT NOT NULL,
    entities_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    topic_class TEXT NULL CHECK (
        topic_class IN ('POLITICS', 'SPORTS', 'ECONOMICS', 'CRYPTO', 'LEGAL', 'GENERAL_NEWS', 'OTHER')
    ),
    subtopic_class TEXT NULL,
    contradiction_hint_class TEXT NULL CHECK (
        contradiction_hint_class IN ('NONE', 'LOW', 'POSSIBLE', 'STRONG')
    ),
    novelty_hint_class TEXT NULL CHECK (
        novelty_hint_class IN ('NEW', 'RECENT_DUPLICATE', 'STALE', 'UNCLEAR')
    ),
    usability_hint_class TEXT NULL CHECK (
        usability_hint_class IN ('HIGH_UTILITY', 'REVIEW', 'LOW_SIGNAL', 'IGNORE')
    ),
    trust_weight_snapshot NUMERIC(6, 5) NOT NULL,
    enrichment_version TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (
        status IN ('SUCCESS', 'ENRICHMENT_ERROR')
    ),
    error_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_external_event_enrichments_run_id
    ON external_event_enrichments (external_event_enrichment_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_event_enrichments_external_event_id
    ON external_event_enrichments (external_event_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_event_enrichments_topic_class
    ON external_event_enrichments (topic_class, created_at DESC);
