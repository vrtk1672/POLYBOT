CREATE TABLE IF NOT EXISTS ranking_snapshots (
    id BIGSERIAL PRIMARY KEY,
    cycle_id UUID NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
    market_snapshot_id BIGINT NOT NULL REFERENCES market_snapshots(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    rank_position INTEGER NULL,
    base_score NUMERIC(10, 4) NULL,
    adaptive_rank NUMERIC(10, 4) NULL,
    selected_flag BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_flag BOOLEAN NOT NULL DEFAULT TRUE,
    reject_reason TEXT NULL,
    ranking_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommendation_action TEXT NULL CHECK (recommendation_action IN ('BUY_YES', 'BUY_NO', 'SKIP')),
    recommendation_confidence NUMERIC(10, 6) NULL,
    recommendation_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cycle_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_ranking_snapshots_cycle_id ON ranking_snapshots (cycle_id);
CREATE INDEX IF NOT EXISTS idx_ranking_snapshots_market_id_created_at
    ON ranking_snapshots (market_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ranking_snapshots_selected_flag ON ranking_snapshots (selected_flag);
