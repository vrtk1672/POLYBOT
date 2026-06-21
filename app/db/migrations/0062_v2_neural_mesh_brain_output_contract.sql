CREATE TABLE IF NOT EXISTS brain_outputs (
    id BIGSERIAL PRIMARY KEY,
    brain_output_id TEXT NOT NULL UNIQUE,
    brain TEXT NOT NULL CHECK (length(trim(brain)) > 0),
    output_type TEXT NOT NULL CHECK (length(trim(output_type)) > 0),
    market_id TEXT NULL,
    position_id TEXT NULL,
    recommendation TEXT NOT NULL CHECK (length(trim(recommendation)) > 0),
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    urgency NUMERIC(10, 6) NULL CHECK (urgency IS NULL OR (urgency >= 0 AND urgency <= 1)),
    risk_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    reasoning_summary TEXT NULL,
    status TEXT NOT NULL CHECK (length(trim(status)) > 0),
    ttl_seconds INTEGER NULL CHECK (ttl_seconds IS NULL OR ttl_seconds >= 0),
    expires_at TIMESTAMPTZ NULL,
    correlation_id TEXT NULL,
    generated_by TEXT NULL,
    model_name TEXT NULL,
    model_version TEXT NULL,
    prompt_version TEXT NULL,
    raw_payload_ref TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_brain_outputs_brain
    ON brain_outputs (brain, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_brain_outputs_market
    ON brain_outputs (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_brain_outputs_position
    ON brain_outputs (position_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_brain_outputs_status
    ON brain_outputs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_brain_outputs_created_desc
    ON brain_outputs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_brain_outputs_correlation
    ON brain_outputs (correlation_id);

CREATE TABLE IF NOT EXISTS brain_output_dependencies (
    id BIGSERIAL PRIMARY KEY,
    brain_output_id TEXT NOT NULL REFERENCES brain_outputs(brain_output_id) ON DELETE CASCADE,
    dependency_type TEXT NOT NULL CHECK (dependency_type IN ('signal', 'brain_output', 'event', 'source')),
    dependency_id TEXT NOT NULL CHECK (length(trim(dependency_id)) > 0),
    dependency_role TEXT NULL,
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_brain_output_dependencies_output
    ON brain_output_dependencies (brain_output_id);

CREATE INDEX IF NOT EXISTS idx_brain_output_dependencies_type_id
    ON brain_output_dependencies (dependency_type, dependency_id);

CREATE TABLE IF NOT EXISTS brain_output_conflicts (
    id BIGSERIAL PRIMARY KEY,
    brain_output_id TEXT NOT NULL REFERENCES brain_outputs(brain_output_id) ON DELETE CASCADE,
    conflicts_with_type TEXT NOT NULL CHECK (conflicts_with_type IN ('brain_output', 'signal', 'source', 'rule')),
    conflicts_with_id TEXT NOT NULL CHECK (length(trim(conflicts_with_id)) > 0),
    conflict_type TEXT NOT NULL CHECK (length(trim(conflict_type)) > 0),
    conflict_reason TEXT NULL,
    conflict_severity NUMERIC(10, 6) NULL CHECK (conflict_severity IS NULL OR (conflict_severity >= 0 AND conflict_severity <= 1)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_brain_output_conflicts_output
    ON brain_output_conflicts (brain_output_id);

CREATE INDEX IF NOT EXISTS idx_brain_output_conflicts_target
    ON brain_output_conflicts (conflicts_with_type, conflicts_with_id);

CREATE INDEX IF NOT EXISTS idx_brain_output_conflicts_severity
    ON brain_output_conflicts (conflict_severity DESC NULLS LAST, created_at DESC);
