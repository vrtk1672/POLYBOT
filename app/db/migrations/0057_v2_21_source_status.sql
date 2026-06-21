CREATE TABLE IF NOT EXISTS source_status (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    configured BOOLEAN NOT NULL DEFAULT FALSE,
    key_required BOOLEAN NOT NULL DEFAULT FALSE,
    key_present BOOLEAN NOT NULL DEFAULT FALSE,
    key_name TEXT,
    endpoint_url TEXT,
    runtime_status TEXT NOT NULL,
    freshness_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    read_only BOOLEAN NOT NULL DEFAULT TRUE,
    mutation_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    success_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_success_at TIMESTAMPTZ,
    last_error_at TIMESTAMPTZ,
    last_latency_ms INTEGER,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT source_status_runtime_status_check
        CHECK (runtime_status IN ('ACTIVE', 'DEGRADED', 'MISSING', 'DISABLED')),
    CONSTRAINT source_status_freshness_status_check
        CHECK (freshness_status IN ('FRESH', 'STALE', 'UNKNOWN')),
    CONSTRAINT source_status_read_only_safety_check
        CHECK (read_only = TRUE AND mutation_allowed = FALSE)
);

CREATE INDEX IF NOT EXISTS idx_source_status_runtime_status
    ON source_status (runtime_status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_status_type
    ON source_status (source_type, source_name);
