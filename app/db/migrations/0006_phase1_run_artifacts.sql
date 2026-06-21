CREATE TABLE IF NOT EXISTS run_artifacts (
    id UUID PRIMARY KEY,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    artifact_scope TEXT NOT NULL,
    path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (path)
);

CREATE INDEX IF NOT EXISTS idx_run_artifacts_cycle_id_created_at
    ON run_artifacts (cycle_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_scope_created_at
    ON run_artifacts (artifact_scope, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_metadata_json
    ON run_artifacts
    USING GIN (metadata_json);
