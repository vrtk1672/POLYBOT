CREATE TABLE IF NOT EXISTS payout_odds_evaluations (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('FRESH_SEED', 'PAPER_CANDIDATE', 'PAPER_INTENT', 'PAPER_POSITION', 'PAPER_CLOSE')),
    subject_id TEXT NOT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    price NUMERIC NULL,
    price_source TEXT NULL,
    stake_usd NUMERIC NULL,
    quantity NUMERIC NULL,
    shares_if_buy NUMERIC NULL,
    payout_if_win NUMERIC NULL,
    profit_if_win NUMERIC NULL,
    max_loss NUMERIC NULL,
    risk_reward NUMERIC NULL,
    implied_probability NUMERIC NULL,
    break_even_probability NUMERIC NULL,
    fair_probability NUMERIC NULL,
    expected_value NUMERIC NULL,
    settlement_value_status TEXT NOT NULL DEFAULT 'OK',
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payout_odds_sources (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES payout_odds_evaluations(evaluation_id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evaluation_id, source_table, source_record_id, source_type)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payout_odds_subject_price
    ON payout_odds_evaluations (subject_type, subject_id, COALESCE(price_source, ''), COALESCE(price::text, ''), settlement_value_status);

CREATE INDEX IF NOT EXISTS idx_payout_odds_subject_created
    ON payout_odds_evaluations (subject_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payout_odds_market_created
    ON payout_odds_evaluations (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payout_odds_status_created
    ON payout_odds_evaluations (settlement_value_status, created_at DESC);
