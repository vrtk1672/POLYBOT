CREATE TABLE IF NOT EXISTS neural_events (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    correlation_id TEXT NULL,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    position_id TEXT NULL,
    source_component TEXT NOT NULL,
    source_type TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    consumed_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PUBLISHED',
    source_table TEXT NULL,
    source_record_id TEXT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT neural_events_priority_chk CHECK (priority BETWEEN 0 AND 10),
    CONSTRAINT neural_events_status_chk CHECK (status IN ('PUBLISHED', 'REPLAYED')),
    CONSTRAINT neural_events_source_type_chk CHECK (source_type IN ('neuron', 'brain', 'risk', 'exit', 'eligibility', 'paper', 'capital', 'memory', 'market', 'runtime', 'system'))
);

CREATE INDEX IF NOT EXISTS idx_neural_events_type_created
    ON neural_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_neural_events_market_created
    ON neural_events (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_neural_events_candidate_created
    ON neural_events (candidate_id, created_at DESC)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_neural_events_position_created
    ON neural_events (position_id, created_at DESC)
    WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_neural_events_correlation_created
    ON neural_events (correlation_id, created_at DESC)
    WHERE correlation_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_neural_events_source_record_type
    ON neural_events (source_table, source_record_id, event_type)
    WHERE source_table IS NOT NULL AND source_record_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS neural_event_consumers (
    id BIGSERIAL PRIMARY KEY,
    consumer_id TEXT NOT NULL UNIQUE,
    consumer_name TEXT NOT NULL UNIQUE,
    interested_event_types TEXT[] NOT NULL DEFAULT '{}',
    source_component TEXT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    last_delivered_event_id TEXT NULL,
    last_delivered_at TIMESTAMPTZ NULL,
    last_error_at TIMESTAMPTZ NULL,
    error_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neural_event_consumers_status_chk CHECK (status IN ('ACTIVE', 'PAUSED', 'DISABLED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS idx_neural_event_consumers_status
    ON neural_event_consumers (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS neural_event_delivery (
    id BIGSERIAL PRIMARY KEY,
    delivery_id TEXT NOT NULL UNIQUE,
    event_id TEXT NOT NULL,
    consumer_id TEXT NOT NULL,
    consumer_name TEXT NOT NULL,
    replay_id TEXT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    delivery_status TEXT NOT NULL,
    error_message TEXT NULL,
    delivered_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT neural_event_delivery_status_chk CHECK (delivery_status IN ('PENDING', 'DELIVERED', 'FAILED', 'SKIPPED', 'REPLAYED'))
);

CREATE INDEX IF NOT EXISTS idx_neural_event_delivery_event
    ON neural_event_delivery (event_id);

CREATE INDEX IF NOT EXISTS idx_neural_event_delivery_consumer
    ON neural_event_delivery (consumer_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_neural_event_delivery_status
    ON neural_event_delivery (delivery_status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_neural_event_delivery_initial
    ON neural_event_delivery (event_id, consumer_name)
    WHERE replay_id IS NULL;

CREATE TABLE IF NOT EXISTS neural_event_replay (
    id BIGSERIAL PRIMARY KEY,
    replay_id TEXT NOT NULL UNIQUE,
    requested_by TEXT NOT NULL,
    reason TEXT NOT NULL,
    filter_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'PENDING',
    matched_count INTEGER NOT NULL DEFAULT 0,
    delivered_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT neural_event_replay_status_chk CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED'))
);

CREATE INDEX IF NOT EXISTS idx_neural_event_replay_created
    ON neural_event_replay (created_at DESC);
