CREATE TABLE IF NOT EXISTS invalidation_reasoning_runs (
    id UUID PRIMARY KEY,
    resolution_analysis_run_id UUID NULL REFERENCES resolution_analysis_runs(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    reasoner_version TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_invalidation_reasoning_runs_started_at
    ON invalidation_reasoning_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_invalidation_reasoning_runs_resolution_analysis_run_id
    ON invalidation_reasoning_runs (resolution_analysis_run_id)
    WHERE resolution_analysis_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS invalidation_reasonings (
    id UUID PRIMARY KEY,
    invalidation_reasoning_run_id UUID NOT NULL REFERENCES invalidation_reasoning_runs(id) ON DELETE CASCADE,
    interpretation_id UUID NOT NULL REFERENCES event_interpretations(id) ON DELETE CASCADE,
    market_link_candidate_id UUID NOT NULL REFERENCES market_link_candidates(id) ON DELETE CASCADE,
    resolution_analysis_id UUID NOT NULL REFERENCES resolution_analyses(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    raw_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasoning_summary TEXT NULL,
    thesis_effect_class TEXT NULL CHECK (
        thesis_effect_class IN (
            'SUPPORTS_THESIS', 'NEUTRAL', 'WARNING', 'CONTRADICTS_THESIS', 'INVALIDATES_THESIS'
        )
    ),
    invalidation_risk_score NUMERIC(6, 5) NULL,
    confidence_degradation_score NUMERIC(6, 5) NULL,
    contradiction_strength_score NUMERIC(6, 5) NULL,
    recommended_monitoring_class TEXT NULL CHECK (
        recommended_monitoring_class IN ('IGNORE', 'WATCH', 'ESCALATE', 'INVALIDATION_CANDIDATE')
    ),
    advisory_action_class TEXT NULL CHECK (
        advisory_action_class IN ('NONE', 'DEGRADE_CONFIDENCE', 'REQUIRE_CONFIRMATION', 'PREPARE_INVALIDATION_REVIEW')
    ),
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (
        status IN ('SUCCESS', 'PARSE_ERROR', 'MODEL_ERROR')
    ),
    error_text TEXT NULL,
    reasoner_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invalidation_reasonings_run_id
    ON invalidation_reasonings (invalidation_reasoning_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_invalidation_reasonings_market_id
    ON invalidation_reasonings (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_invalidation_reasonings_resolution_analysis_id
    ON invalidation_reasonings (resolution_analysis_id, created_at DESC);
