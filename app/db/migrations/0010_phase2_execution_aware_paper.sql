CREATE TABLE IF NOT EXISTS paper_orders (
    id UUID PRIMARY KEY,
    paper_run_id UUID NOT NULL REFERENCES paper_runs(id) ON DELETE CASCADE,
    paper_signal_id UUID NOT NULL REFERENCES paper_signals(id) ON DELETE CASCADE,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    intended_outcome TEXT NOT NULL,
    action TEXT NOT NULL,
    intended_price NUMERIC(10, 6) NOT NULL,
    intended_size NUMERIC(18, 6) NOT NULL,
    notional NUMERIC(18, 6) NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('CREATED', 'BLOCKED_MIN_SIZE', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'EXPIRED')
    ),
    fill_ratio NUMERIC(10, 6) NOT NULL DEFAULT 0,
    filled_size NUMERIC(18, 6) NOT NULL DEFAULT 0,
    remaining_size NUMERIC(18, 6) NOT NULL DEFAULT 0,
    avg_fill_price NUMERIC(10, 6) NULL,
    min_size_check_passed BOOLEAN NOT NULL DEFAULT FALSE,
    stale_at TIMESTAMPTZ NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (paper_signal_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_orders_run_status_created_at
    ON paper_orders (paper_run_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_orders_market_status_created_at
    ON paper_orders (market_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_order_events (
    id UUID PRIMARY KEY,
    paper_order_id UUID NOT NULL REFERENCES paper_orders(id) ON DELETE CASCADE,
    event_at TIMESTAMPTZ NOT NULL,
    old_status TEXT NULL,
    new_status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_order_events_order_id_event_at
    ON paper_order_events (paper_order_id, event_at ASC);

CREATE TABLE IF NOT EXISTS paper_positions (
    id UUID PRIMARY KEY,
    paper_run_id UUID NOT NULL REFERENCES paper_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    intended_outcome TEXT NOT NULL,
    size NUMERIC(18, 6) NOT NULL DEFAULT 0,
    avg_entry NUMERIC(10, 6) NULL,
    mark_price NUMERIC(10, 6) NULL,
    unrealized NUMERIC(18, 6) NULL,
    realized NUMERIC(18, 6) NULL,
    current_status TEXT NOT NULL,
    thesis_state TEXT NOT NULL,
    invalidation_state TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_paper_positions_run_status_updated_at
    ON paper_positions (paper_run_id, current_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_positions_market_status_updated_at
    ON paper_positions (market_id, current_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS paper_position_events (
    id UUID PRIMARY KEY,
    paper_position_id UUID NOT NULL REFERENCES paper_positions(id) ON DELETE CASCADE,
    event_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_position_events_position_id_event_at
    ON paper_position_events (paper_position_id, event_at ASC);
