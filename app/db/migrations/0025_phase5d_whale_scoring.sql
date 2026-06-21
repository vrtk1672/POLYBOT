CREATE TABLE IF NOT EXISTS whale_scoring_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    scorer_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_scoring_runs_started_at
    ON whale_scoring_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS whale_market_scores (
    id UUID PRIMARY KEY,
    whale_scoring_run_id UUID NOT NULL REFERENCES whale_scoring_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    scoring_window_start TIMESTAMPTZ NULL,
    scoring_window_end TIMESTAMPTZ NULL,
    whale_presence_score NUMERIC(6, 5) NOT NULL,
    whale_conviction_score NUMERIC(6, 5) NOT NULL,
    smart_whale_alignment_score NUMERIC(6, 5) NOT NULL,
    whale_reversal_risk NUMERIC(6, 5) NOT NULL,
    supporting_wallet_count INTEGER NOT NULL DEFAULT 0,
    top_supporting_wallets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    category_mix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    scoring_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    scoring_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    scorer_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_market_scores_run_id
    ON whale_market_scores (whale_scoring_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_whale_market_scores_market
    ON whale_market_scores (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_whale_market_scores_presence
    ON whale_market_scores (whale_presence_score DESC, created_at DESC);
