CREATE TABLE IF NOT EXISTS market_snapshots (
    id BIGSERIAL PRIMARY KEY,
    cycle_id UUID NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    event_id TEXT NULL,
    question TEXT NOT NULL,
    slug TEXT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    yes_price NUMERIC(10, 6) NULL,
    no_price NUMERIC(10, 6) NULL,
    last_trade_price NUMERIC(10, 6) NULL,
    best_bid NUMERIC(10, 6) NULL,
    best_ask NUMERIC(10, 6) NULL,
    spread NUMERIC(10, 6) NULL,
    tick_size NUMERIC(10, 6) NULL,
    liquidity NUMERIC(18, 4) NULL,
    volume NUMERIC(18, 4) NULL,
    volume_24h NUMERIC(18, 4) NULL,
    open_interest NUMERIC(18, 4) NULL,
    comment_count INTEGER NULL,
    competitive NUMERIC(10, 6) NULL,
    neg_risk BOOLEAN NULL,
    orderbook_enabled BOOLEAN NULL,
    accepting_orders BOOLEAN NOT NULL DEFAULT FALSE,
    time_to_close_seconds INTEGER NULL,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cycle_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_cycle_id ON market_snapshots (cycle_id);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_market_id_captured_at
    ON market_snapshots (market_id, captured_at DESC);
