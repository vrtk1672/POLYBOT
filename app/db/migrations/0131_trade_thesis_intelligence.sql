CREATE TABLE IF NOT EXISTS trade_thesis_evaluations (
    id BIGSERIAL PRIMARY KEY,
    thesis_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('PAPER_POSITION','PAPER_CANDIDATE','PAPER_INTENT','FRESH_SEED')),
    subject_id TEXT NOT NULL,
    candidate_id TEXT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    source_refresh_cycle_id TEXT NULL,
    edge_thesis_id TEXT NULL,
    risk_evidence_id TEXT NULL,
    trade_thesis_type TEXT NOT NULL,
    exit_intent TEXT NOT NULL,
    entry_reason TEXT NOT NULL,
    primary_catalyst TEXT NULL,
    supporting_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    opposing_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    entry_price NUMERIC NULL,
    target_exit_price NUMERIC NULL,
    stop_or_invalidation_price NUMERIC NULL,
    expected_hold_time_hours NUMERIC NULL,
    max_hold_time_hours NUMERIC NULL,
    hold_time_source TEXT NOT NULL,
    expected_price_move NUMERIC NULL,
    expected_reward NUMERIC NULL,
    reward_source TEXT NULL,
    exit_trigger TEXT NULL,
    invalidation_condition TEXT NULL,
    time_stop_condition TEXT NULL,
    thesis_confidence NUMERIC NULL,
    exit_confidence NUMERIC NULL,
    ai_review_state TEXT NOT NULL,
    ai_thesis TEXT NULL,
    ai_counter_thesis TEXT NULL,
    status TEXT NOT NULL,
    blocker_code TEXT NULL,
    required_to_pass_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_thesis_subject_created
    ON trade_thesis_evaluations (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_thesis_candidate_created
    ON trade_thesis_evaluations (candidate_id, created_at DESC)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_trade_thesis_market_created
    ON trade_thesis_evaluations (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_trade_thesis_status_created
    ON trade_thesis_evaluations (status, created_at DESC);
