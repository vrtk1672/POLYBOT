-- V2 Neural Mesh Part 4C-M: Orderbook Snapshot Foundation.
-- Data-only orderbook truth. No orders, intents, fills, positions, risk approvals, or exits.

ALTER TABLE orderbook_snapshots
    ADD COLUMN IF NOT EXISTS depth_bid_1c NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS depth_ask_1c NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS depth_bid_2c NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS depth_ask_2c NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS depth_bid_5c NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS depth_ask_5c NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS total_bid_depth NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS total_ask_depth NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS liquidity_score NUMERIC NULL,
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS snapshot_status TEXT NOT NULL DEFAULT 'OK',
    ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stale_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS raw_payload_ref TEXT NULL,
    ADD COLUMN IF NOT EXISTS correlation_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE orderbook_snapshots
SET collected_at = COALESCE(collected_at, snapshot_at)
WHERE collected_at IS NULL;

ALTER TABLE orderbook_snapshots
    ALTER COLUMN collected_at SET DEFAULT now(),
    ALTER COLUMN collected_at SET NOT NULL;

ALTER TABLE orderbook_snapshots
    DROP CONSTRAINT IF EXISTS orderbook_snapshots_snapshot_status_check;

ALTER TABLE orderbook_snapshots
    ADD CONSTRAINT orderbook_snapshots_snapshot_status_check
    CHECK (snapshot_status IN ('OK', 'PARTIAL', 'EMPTY', 'STALE', 'ERROR'));

CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_source ON orderbook_snapshots (source);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_status ON orderbook_snapshots (snapshot_status);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_is_stale ON orderbook_snapshots (is_stale);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_collected_at ON orderbook_snapshots (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_liquidity_score ON orderbook_snapshots (liquidity_score);

CREATE TABLE IF NOT EXISTS orderbook_snapshot_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'OK',
    markets_checked INTEGER NOT NULL DEFAULT 0 CHECK (markets_checked >= 0),
    snapshots_created INTEGER NOT NULL DEFAULT 0 CHECK (snapshots_created >= 0),
    snapshots_updated INTEGER NOT NULL DEFAULT 0 CHECK (snapshots_updated >= 0),
    ok_snapshots INTEGER NOT NULL DEFAULT 0 CHECK (ok_snapshots >= 0),
    partial_orderbooks INTEGER NOT NULL DEFAULT 0 CHECK (partial_orderbooks >= 0),
    empty_orderbooks INTEGER NOT NULL DEFAULT 0 CHECK (empty_orderbooks >= 0),
    stale_count INTEGER NOT NULL DEFAULT 0 CHECK (stale_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    paper_ready_before BOOLEAN NOT NULL DEFAULT FALSE CHECK (paper_ready_before = FALSE),
    paper_ready_after BOOLEAN NOT NULL DEFAULT FALSE CHECK (paper_ready_after = FALSE),
    orders_created INTEGER NOT NULL DEFAULT 0 CHECK (orders_created = 0),
    order_intents_created INTEGER NOT NULL DEFAULT 0 CHECK (order_intents_created = 0),
    fills_created INTEGER NOT NULL DEFAULT 0 CHECK (fills_created = 0),
    positions_created INTEGER NOT NULL DEFAULT 0 CHECK (positions_created = 0),
    live_actions_created INTEGER NOT NULL DEFAULT 0 CHECK (live_actions_created = 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orderbook_snapshot_runs_started_at ON orderbook_snapshot_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshot_runs_status ON orderbook_snapshot_runs (status);
