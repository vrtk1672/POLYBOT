-- Last-mile PAPER runtime orderbook refresh diagnostics.
-- Non-destructive: records targeted refresh attempts and adds read-only
-- diagnostics to paper_runtime_decisions.

CREATE TABLE IF NOT EXISTS last_mile_orderbook_refresh_attempts (
    id BIGSERIAL PRIMARY KEY,
    attempt_id TEXT NOT NULL UNIQUE,
    decision_id TEXT,
    source_review_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    token_id TEXT,
    side TEXT,
    refresh_state TEXT NOT NULL,
    refresh_error TEXT,
    pre_refresh_snapshot_id BIGINT,
    pre_refresh_age_seconds NUMERIC,
    post_refresh_snapshot_id BIGINT,
    post_refresh_age_seconds NUMERIC,
    orderbook_ttl_seconds INTEGER NOT NULL DEFAULT 180,
    stale_cleared BOOLEAN NOT NULL DEFAULT FALSE,
    connector_latency_ms INTEGER,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_last_mile_orderbook_market_token_side
    ON last_mile_orderbook_refresh_attempts (market_id, token_id, side, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_last_mile_orderbook_decision
    ON last_mile_orderbook_refresh_attempts (decision_id, started_at DESC);

ALTER TABLE paper_runtime_decisions
    ADD COLUMN IF NOT EXISTS orderbook_age_seconds NUMERIC,
    ADD COLUMN IF NOT EXISTS orderbook_ttl_seconds INTEGER NOT NULL DEFAULT 180,
    ADD COLUMN IF NOT EXISTS last_mile_refresh_attempted BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_mile_refresh_state TEXT,
    ADD COLUMN IF NOT EXISTS last_mile_refresh_error TEXT,
    ADD COLUMN IF NOT EXISTS post_refresh_orderbook_state TEXT;

CREATE INDEX IF NOT EXISTS idx_paper_runtime_decisions_last_mile
    ON paper_runtime_decisions (last_mile_refresh_attempted, last_mile_refresh_state, updated_at DESC);
