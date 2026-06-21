CREATE TABLE IF NOT EXISTS market_link_runs (
    id UUID PRIMARY KEY,
    interpretation_run_id UUID NULL REFERENCES event_interpretation_runs(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    linker_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_link_runs_started_at
    ON market_link_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_link_runs_interpretation_run_id
    ON market_link_runs (interpretation_run_id)
    WHERE interpretation_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS market_link_candidates (
    id UUID PRIMARY KEY,
    market_link_run_id UUID NOT NULL REFERENCES market_link_runs(id) ON DELETE CASCADE,
    interpretation_id UUID NOT NULL REFERENCES event_interpretations(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    candidate_source TEXT NOT NULL CHECK (
        candidate_source IN (
            'INTERPRETER_MARKET_ID', 'TITLE_MATCH', 'SLUG_MATCH', 'KEYWORD_MATCH', 'MANUAL_REF'
        )
    ),
    link_status TEXT NOT NULL CHECK (
        link_status IN ('CANDIDATE', 'STRONG_CANDIDATE', 'NEEDS_REVIEW', 'REJECTED')
    ),
    relevance_score NUMERIC(6, 5) NOT NULL,
    directness_class TEXT NULL,
    directness_score NUMERIC(6, 5) NULL,
    contradiction_risk NUMERIC(6, 5) NULL,
    affected_outcome TEXT NULL,
    usability_class TEXT NOT NULL CHECK (
        usability_class IN ('USABLE_NOW', 'NEEDS_CONFIRMATION', 'TOO_AMBIGUOUS', 'IRRELEVANT')
    ),
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    linker_version TEXT NOT NULL,
    prompt_version TEXT NULL,
    model_name TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_link_candidates_run_id
    ON market_link_candidates (market_link_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_link_candidates_interpretation_id
    ON market_link_candidates (interpretation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_link_candidates_market_id
    ON market_link_candidates (market_id, created_at DESC);
