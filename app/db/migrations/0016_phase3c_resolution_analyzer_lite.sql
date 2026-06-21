CREATE TABLE IF NOT EXISTS resolution_analysis_runs (
    id UUID PRIMARY KEY,
    market_link_run_id UUID NULL REFERENCES market_link_runs(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    analyzer_version TEXT NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_resolution_analysis_runs_started_at
    ON resolution_analysis_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_resolution_analysis_runs_market_link_run_id
    ON resolution_analysis_runs (market_link_run_id)
    WHERE market_link_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS resolution_analyses (
    id UUID PRIMARY KEY,
    resolution_analysis_run_id UUID NOT NULL REFERENCES resolution_analysis_runs(id) ON DELETE CASCADE,
    interpretation_id UUID NOT NULL REFERENCES event_interpretations(id) ON DELETE CASCADE,
    market_link_candidate_id UUID NOT NULL REFERENCES market_link_candidates(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    raw_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolution_summary TEXT NULL,
    wording_clarity_score NUMERIC(6, 5) NULL,
    ambiguity_risk_score NUMERIC(6, 5) NULL,
    resolution_mismatch_risk NUMERIC(6, 5) NULL,
    resolution_confidence_score NUMERIC(6, 5) NULL,
    direct_fit_class TEXT NULL CHECK (
        direct_fit_class IN ('DIRECT_FIT', 'PLAUSIBLE_BUT_RISKY', 'AMBIGUOUS', 'POOR_FIT')
    ),
    usable_now_class TEXT NULL CHECK (
        usable_now_class IN ('USABLE_NOW', 'NEEDS_CONFIRMATION', 'TOO_AMBIGUOUS', 'DO_NOT_USE')
    ),
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (
        status IN ('SUCCESS', 'PARSE_ERROR', 'MODEL_ERROR')
    ),
    error_text TEXT NULL,
    analyzer_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_resolution_analyses_run_id
    ON resolution_analyses (resolution_analysis_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_resolution_analyses_market_id
    ON resolution_analyses (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_resolution_analyses_candidate_id
    ON resolution_analyses (market_link_candidate_id, created_at DESC);
