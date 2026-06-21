CREATE TABLE IF NOT EXISTS live_orders (
    id UUID PRIMARY KEY,
    client_order_id TEXT NOT NULL UNIQUE,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    decision_id UUID NULL REFERENCES decision_ledger(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NOT NULL,
    side TEXT NOT NULL,
    action TEXT NOT NULL,
    price NUMERIC(10, 6) NOT NULL,
    size NUMERIC(18, 6) NOT NULL,
    notional NUMERIC(18, 6) NOT NULL,
    status TEXT NOT NULL,
    exchange_status TEXT NULL,
    exchange_order_id TEXT NULL,
    raw_request JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_live_orders_exchange_order_id
    ON live_orders (exchange_order_id)
    WHERE exchange_order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_live_orders_cycle_id ON live_orders (cycle_id);
CREATE INDEX IF NOT EXISTS idx_live_orders_market_id_created_at
    ON live_orders (market_id, created_at DESC);

CREATE TABLE IF NOT EXISTS order_status_history (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES live_orders(id) ON DELETE CASCADE,
    event_at TIMESTAMPTZ NOT NULL,
    old_status TEXT NULL,
    new_status TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT NULL,
    exchange_status TEXT NULL,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_order_status_history_order_id_event_at
    ON order_status_history (order_id, event_at ASC);

CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    size NUMERIC(18, 6) NOT NULL DEFAULT 0,
    avg_entry NUMERIC(10, 6) NULL,
    current_status TEXT NOT NULL,
    unrealized NUMERIC(18, 6) NOT NULL DEFAULT 0,
    realized NUMERIC(18, 6) NOT NULL DEFAULT 0,
    thesis_state TEXT NOT NULL,
    invalidation_state TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_positions_market_side_status
    ON positions (market_id, side, current_status);

CREATE TABLE IF NOT EXISTS position_events (
    id UUID PRIMARY KEY,
    position_id UUID NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    event_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_position_events_position_id_event_at
    ON position_events (position_id, event_at ASC);
