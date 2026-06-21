CREATE TABLE IF NOT EXISTS cycles (
    id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'COMPLETED', 'FAILED', 'PARTIAL')),
    mode TEXT NOT NULL CHECK (mode IN ('SCAN_ONLY', 'PAPER', 'LIVE_DRY_RUN', 'LIVE_SUBMIT')),
    trigger_source TEXT NOT NULL,
    session_id TEXT NULL,
    top_n INTEGER NOT NULL,
    pages_requested INTEGER NULL,
    markets_fetched_count INTEGER NOT NULL DEFAULT 0,
    markets_scored_count INTEGER NOT NULL DEFAULT 0,
    markets_ranked_count INTEGER NOT NULL DEFAULT 0,
    decisions_count INTEGER NOT NULL DEFAULT 0,
    selected_market_id TEXT NULL,
    last_error TEXT NULL,
    runtime_ms INTEGER NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cycles_started_at ON cycles (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycles_status_started_at ON cycles (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycles_selected_market_id ON cycles (selected_market_id);
