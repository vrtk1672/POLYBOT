-- Runtime truth + decision diversity metadata.
-- Non-destructive: preserves historical runtime cycles and paper decisions.

ALTER TABLE paper_runtime_decisions
    ADD COLUMN IF NOT EXISTS decision_batch_id TEXT,
    ADD COLUMN IF NOT EXISTS selection_rank INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS market_side_rank INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS diversity_score NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS duplicate_suppressed_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_current_batch BOOLEAN NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_paper_runtime_decisions_current_batch
    ON paper_runtime_decisions (is_current_batch, decision, paper_enter_allowed, diversity_score DESC, opportunity_score DESC);

CREATE INDEX IF NOT EXISTS idx_paper_runtime_decisions_market_side_current
    ON paper_runtime_decisions (market_id, side, is_current_batch);

CREATE INDEX IF NOT EXISTS idx_runtime_cycles_v2_open_status_started
    ON runtime_cycles_v2 (status, started_at DESC)
    WHERE finished_at IS NULL;
