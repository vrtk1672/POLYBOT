CREATE TABLE IF NOT EXISTS cognition_summary_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    narrator_version TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_cognition_summary_runs_started_at
    ON cognition_summary_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS cognition_summaries (
    id UUID PRIMARY KEY,
    cognition_summary_run_id UUID NOT NULL REFERENCES cognition_summary_runs(id) ON DELETE CASCADE,
    interpretation_id UUID NOT NULL REFERENCES event_interpretations(id) ON DELETE CASCADE,
    market_link_candidate_id UUID NOT NULL REFERENCES market_link_candidates(id) ON DELETE CASCADE,
    resolution_analysis_id UUID NOT NULL REFERENCES resolution_analyses(id) ON DELETE CASCADE,
    invalidation_reasoning_id UUID NOT NULL REFERENCES invalidation_reasonings(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    event_summary_snapshot TEXT NOT NULL,
    raw_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    narration_summary TEXT NULL,
    concise_narration_text TEXT NULL,
    cognition_conclusion_class TEXT NULL CHECK (
        cognition_conclusion_class IN (
            'SUPPORTIVE', 'WATCHFUL', 'RISKY', 'CONTRADICTORY', 'INVALIDATION_CANDIDATE'
        )
    ),
    overall_confidence_score NUMERIC(6, 5) NULL,
    caution_score NUMERIC(6, 5) NULL,
    usability_class TEXT NULL CHECK (
        usability_class IN ('USABLE_NOW', 'NEEDS_CONFIRMATION', 'TOO_AMBIGUOUS', 'DO_NOT_USE')
    ),
    recommended_operator_focus TEXT NULL CHECK (
        recommended_operator_focus IN (
            'NONE', 'MONITOR', 'REVIEW_LINKING', 'REVIEW_RESOLUTION', 'REVIEW_INVALIDATION'
        )
    ),
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (
        status IN ('SUCCESS', 'PARSE_ERROR', 'MODEL_ERROR')
    ),
    error_text TEXT NULL,
    narrator_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cognition_summaries_run_id
    ON cognition_summaries (cognition_summary_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cognition_summaries_market_id
    ON cognition_summaries (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cognition_summaries_invalidation_reasoning_id
    ON cognition_summaries (invalidation_reasoning_id, created_at DESC);
