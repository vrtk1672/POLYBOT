CREATE TABLE IF NOT EXISTS ranking_policy_runs (
    id UUID PRIMARY KEY,
    ranking_v2_run_id UUID NULL REFERENCES ranking_v2_runs(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    policy_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ranking_policy_runs_started_at
    ON ranking_policy_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS ranking_policy_candidates (
    id UUID PRIMARY KEY,
    ranking_policy_run_id UUID NOT NULL REFERENCES ranking_policy_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    ranking_v2_candidate_id UUID NOT NULL REFERENCES ranking_v2_candidates(id) ON DELETE CASCADE,
    total_rank_score NUMERIC(7, 4) NOT NULL,
    rank_position INTEGER NOT NULL,
    rank_tier_class TEXT NOT NULL CHECK (
        rank_tier_class IN ('TOP', 'HIGH', 'MEDIUM', 'LOW', 'REJECT')
    ),
    gate_decision_class TEXT NOT NULL CHECK (
        gate_decision_class IN ('SELECTABLE', 'REVIEW_ONLY', 'BLOCKED', 'HARD_REJECT')
    ),
    gate_priority_class TEXT NOT NULL CHECK (
        gate_priority_class IN ('PRIMARY', 'SECONDARY', 'RESERVE', 'NONE')
    ),
    max_selected_within_run INTEGER NOT NULL,
    selection_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    selection_reason_text TEXT NOT NULL,
    policy_explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ranking_policy_candidates_run_id
    ON ranking_policy_candidates (ranking_policy_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ranking_policy_candidates_market
    ON ranking_policy_candidates (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ranking_policy_candidates_decision
    ON ranking_policy_candidates (gate_decision_class, gate_priority_class, created_at DESC);
