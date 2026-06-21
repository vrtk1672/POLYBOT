CREATE TABLE IF NOT EXISTS ranking_v2_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    ranking_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ranking_v2_runs_started_at
    ON ranking_v2_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS ranking_v2_candidates (
    id UUID PRIMARY KEY,
    ranking_v2_run_id UUID NOT NULL REFERENCES ranking_v2_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    market_snapshot_id BIGINT NULL REFERENCES market_snapshots(id) ON DELETE SET NULL,
    decision_id UUID NULL REFERENCES decision_ledger(id) ON DELETE SET NULL,
    cognition_summary_id UUID NULL REFERENCES cognition_summaries(id) ON DELETE SET NULL,
    whale_market_score_id UUID NULL REFERENCES whale_market_scores(id) ON DELETE SET NULL,
    trade_classification_id UUID NULL REFERENCES trade_classifications(id) ON DELETE SET NULL,
    bucket_allocation_id UUID NULL REFERENCES bucket_allocations(id) ON DELETE SET NULL,
    total_rank_score NUMERIC(7, 4) NOT NULL,
    factor_scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    rank_position INTEGER NOT NULL,
    rank_tier_class TEXT NOT NULL CHECK (
        rank_tier_class IN ('TOP', 'HIGH', 'MEDIUM', 'LOW', 'REJECT')
    ),
    rank_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    rank_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ranking_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ranking_v2_candidates_run_id
    ON ranking_v2_candidates (ranking_v2_run_id, rank_position ASC);

CREATE INDEX IF NOT EXISTS idx_ranking_v2_candidates_market
    ON ranking_v2_candidates (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ranking_v2_candidates_score
    ON ranking_v2_candidates (total_rank_score DESC, created_at DESC);
