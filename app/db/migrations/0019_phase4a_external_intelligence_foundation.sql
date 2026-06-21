CREATE TABLE IF NOT EXISTS intelligence_sources (
    id UUID PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('RSS', 'OFFICIAL_SITE', 'NEWS_SITE', 'MANUAL_IMPORT', 'ECONOMIC_FEED', 'SPORTS_FEED')
    ),
    base_url TEXT NULL,
    category TEXT NOT NULL,
    trust_weight NUMERIC(6, 5) NOT NULL,
    latency_score NUMERIC(6, 5) NULL,
    noise_score NUMERIC(6, 5) NULL,
    relevance_scope TEXT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_intelligence_sources_enabled
    ON intelligence_sources (is_enabled, source_type);

CREATE TABLE IF NOT EXISTS intelligence_ingestion_runs (
    id UUID PRIMARY KEY,
    intelligence_source_id UUID NULL REFERENCES intelligence_sources(id) ON DELETE SET NULL,
    run_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    fetched_count INTEGER NOT NULL DEFAULT 0,
    normalized_count INTEGER NOT NULL DEFAULT 0,
    deduped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_intelligence_ingestion_runs_started_at
    ON intelligence_ingestion_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS external_raw_events (
    id UUID PRIMARY KEY,
    intelligence_ingestion_run_id UUID NOT NULL REFERENCES intelligence_ingestion_runs(id) ON DELETE CASCADE,
    intelligence_source_id UUID NOT NULL REFERENCES intelligence_sources(id) ON DELETE CASCADE,
    source_event_id TEXT NULL,
    source_url TEXT NULL,
    source_published_at TIMESTAMPTZ NULL,
    source_title TEXT NULL,
    raw_content_text TEXT NULL,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_hash TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_external_raw_events_run_id
    ON external_raw_events (intelligence_ingestion_run_id, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_raw_events_raw_hash
    ON external_raw_events (raw_hash, fetched_at DESC);

CREATE TABLE IF NOT EXISTS external_events_normalized (
    id UUID PRIMARY KEY,
    external_raw_event_id UUID NOT NULL REFERENCES external_raw_events(id) ON DELETE CASCADE,
    intelligence_source_id UUID NOT NULL REFERENCES intelligence_sources(id) ON DELETE CASCADE,
    normalized_title TEXT NOT NULL,
    normalized_summary TEXT NOT NULL,
    published_at TIMESTAMPTZ NULL,
    canonical_url TEXT NULL,
    canonical_hash TEXT NOT NULL,
    event_language TEXT NULL,
    source_category TEXT NOT NULL,
    trust_weight_snapshot NUMERIC(6, 5) NOT NULL,
    dedupe_key TEXT NOT NULL,
    normalization_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('READY', 'DUPLICATE', 'NORMALIZATION_ERROR')
    ),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_external_events_normalized_run_lookup
    ON external_events_normalized (external_raw_event_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_events_normalized_dedupe_key
    ON external_events_normalized (dedupe_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_events_normalized_canonical_hash
    ON external_events_normalized (canonical_hash, created_at DESC);
