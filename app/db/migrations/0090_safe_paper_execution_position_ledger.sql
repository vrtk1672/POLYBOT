CREATE TABLE IF NOT EXISTS paper_fills (
    id BIGSERIAL PRIMARY KEY,
    paper_fill_id TEXT NOT NULL UNIQUE,
    paper_order_id UUID NOT NULL REFERENCES paper_orders(id) ON DELETE CASCADE,
    source_intent_id TEXT NOT NULL REFERENCES paper_intents(paper_intent_id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    fill_price NUMERIC(18, 8) NOT NULL CHECK (fill_price >= 0 AND fill_price <= 1),
    quantity NUMERIC(18, 8) NOT NULL CHECK (quantity > 0),
    price_basis TEXT NOT NULL,
    orderbook_snapshot_id BIGINT NULL REFERENCES orderbook_snapshots(id) ON DELETE SET NULL,
    slippage_estimate NUMERIC(18, 8) NULL,
    correlation_id TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_fills_order
    ON paper_fills (paper_order_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_fills_source_intent
    ON paper_fills (source_intent_id);

CREATE INDEX IF NOT EXISTS idx_paper_fills_market_created
    ON paper_fills (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_fills_snapshot
    ON paper_fills (orderbook_snapshot_id)
    WHERE orderbook_snapshot_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS paper_execution_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL DEFAULT 'ON',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    intents_checked INTEGER NOT NULL DEFAULT 0 CHECK (intents_checked >= 0),
    executable_intents INTEGER NOT NULL DEFAULT 0 CHECK (executable_intents >= 0),
    orders_created INTEGER NOT NULL DEFAULT 0 CHECK (orders_created >= 0),
    fills_created INTEGER NOT NULL DEFAULT 0 CHECK (fills_created >= 0),
    positions_created INTEGER NOT NULL DEFAULT 0 CHECK (positions_created >= 0),
    blocked_intents INTEGER NOT NULL DEFAULT 0 CHECK (blocked_intents >= 0),
    duplicate_skipped INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_skipped >= 0),
    block_reasons_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    fills_v2_delta INTEGER NOT NULL DEFAULT 0 CHECK (fills_v2_delta >= 0),
    positions_delta INTEGER NOT NULL DEFAULT 0 CHECK (positions_delta >= 0),
    error_message TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT paper_execution_runs_status_check CHECK (
        status IN (
            'OK',
            'NO_VALID_PAPER_INTENTS',
            'PAPER_BLOCKED_BY_MODE',
            'SYSTEM_POWER_OFF',
            'DEGRADED',
            'ERROR'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_paper_execution_runs_created
    ON paper_execution_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_execution_runs_status
    ON paper_execution_runs (status, created_at DESC);
