CREATE TABLE IF NOT EXISTS event_interpretation_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_interpretation_runs_started_at
    ON event_interpretation_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS event_interpretations (
    id UUID PRIMARY KEY,
    interpretation_run_id UUID NOT NULL REFERENCES event_interpretation_runs(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('SUCCESS', 'PARSE_ERROR', 'MODEL_ERROR')
    ),
    error_text TEXT NULL,
    raw_event_text TEXT NOT NULL,
    raw_event_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    normalized_event_title TEXT NULL,
    event_type TEXT NULL,
    event_summary TEXT NULL,
    certainty_score NUMERIC(6, 5) NULL,
    ambiguity_score NUMERIC(6, 5) NULL,
    novelty_score NUMERIC(6, 5) NULL,
    directness_class TEXT NULL,
    directness_score NUMERIC(6, 5) NULL,
    contradiction_risk NUMERIC(6, 5) NULL,
    affected_market_candidates_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    affected_outcomes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_action_class TEXT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_event_interpretations_run_created_at
    ON event_interpretations (interpretation_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_event_interpretations_created_at
    ON event_interpretations (created_at DESC);
