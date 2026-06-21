CREATE TABLE IF NOT EXISTS event_log (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NULL,
    aggregate_id TEXT NULL,
    source_service TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_id TEXT NULL,
    cycle_id TEXT NULL,
    mode TEXT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    stored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_event_log_event_type ON event_log (event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_aggregate ON event_log (aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_event_log_correlation_id ON event_log (correlation_id);
CREATE INDEX IF NOT EXISTS idx_event_log_cycle_id ON event_log (cycle_id);
CREATE INDEX IF NOT EXISTS idx_event_log_occurred_at ON event_log (occurred_at);
CREATE INDEX IF NOT EXISTS idx_event_log_stored_at ON event_log (stored_at);

CREATE TABLE IF NOT EXISTS event_consumers (
    id BIGSERIAL PRIMARY KEY,
    consumer_name TEXT NOT NULL UNIQUE,
    consumer_group TEXT NULL,
    subscribed_event_types TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    last_seen_at TIMESTAMPTZ NULL,
    last_event_id TEXT NULL,
    last_success_at TIMESTAMPTZ NULL,
    last_error_at TIMESTAMPTZ NULL,
    error_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT event_consumers_status_chk CHECK (status IN ('ACTIVE', 'PAUSED', 'ERROR', 'DISABLED'))
);

CREATE TABLE IF NOT EXISTS event_delivery_attempts (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    next_retry_at TIMESTAMPTZ NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT event_delivery_attempts_status_chk CHECK (status IN ('PENDING', 'SUCCESS', 'FAILED', 'RETRY_SCHEDULED', 'DLQ'))
);

CREATE INDEX IF NOT EXISTS idx_event_delivery_attempts_event_id ON event_delivery_attempts (event_id);
CREATE INDEX IF NOT EXISTS idx_event_delivery_attempts_consumer_name ON event_delivery_attempts (consumer_name);
CREATE INDEX IF NOT EXISTS idx_event_delivery_attempts_status ON event_delivery_attempts (status);
CREATE INDEX IF NOT EXISTS idx_event_delivery_attempts_next_retry_at ON event_delivery_attempts (next_retry_at);
CREATE INDEX IF NOT EXISTS idx_event_delivery_attempts_started_at ON event_delivery_attempts (started_at);

CREATE TABLE IF NOT EXISTS event_dlq (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    error_message TEXT NULL,
    failed_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT event_dlq_status_chk CHECK (status IN ('OPEN', 'REPLAYED', 'IGNORED', 'RESOLVED'))
);

CREATE INDEX IF NOT EXISTS idx_event_dlq_event_id ON event_dlq (event_id);
CREATE INDEX IF NOT EXISTS idx_event_dlq_consumer_name ON event_dlq (consumer_name);
CREATE INDEX IF NOT EXISTS idx_event_dlq_status ON event_dlq (status);
CREATE INDEX IF NOT EXISTS idx_event_dlq_created_at ON event_dlq (created_at);

CREATE TABLE IF NOT EXISTS event_replay_jobs (
    id BIGSERIAL PRIMARY KEY,
    replay_id TEXT NOT NULL UNIQUE,
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    filter_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    replayed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT event_replay_jobs_status_chk CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'))
);
