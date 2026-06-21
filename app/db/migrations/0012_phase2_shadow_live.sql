CREATE TABLE IF NOT EXISTS shadow_runs (
    id UUID PRIMARY KEY,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    markets_seen_count INTEGER NOT NULL DEFAULT 0,
    markets_ranked_count INTEGER NOT NULL DEFAULT 0,
    candidates_selected_count INTEGER NOT NULL DEFAULT 0,
    shadow_orders_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shadow_runs_cycle_id_started_at
    ON shadow_runs (cycle_id, started_at DESC);

CREATE TABLE IF NOT EXISTS shadow_orders (
    id UUID PRIMARY KEY,
    shadow_run_id UUID NOT NULL REFERENCES shadow_runs(id) ON DELETE CASCADE,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    decision_id UUID NULL REFERENCES decision_ledger(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    token_id TEXT NULL,
    intended_outcome TEXT NULL,
    action TEXT NOT NULL,
    intended_price NUMERIC(10, 6) NULL,
    intended_size NUMERIC(18, 6) NULL,
    notional NUMERIC(18, 6) NULL,
    guard_result TEXT NOT NULL,
    execution_policy_result TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('CREATED', 'BLOCKED', 'WOULD_SUBMIT')
    ),
    raw_intent_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_guard_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (shadow_run_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_shadow_orders_run_status_created_at
    ON shadow_orders (shadow_run_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS shadow_order_events (
    id UUID PRIMARY KEY,
    shadow_order_id UUID NOT NULL REFERENCES shadow_orders(id) ON DELETE CASCADE,
    event_at TIMESTAMPTZ NOT NULL,
    old_status TEXT NULL,
    new_status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shadow_order_events_order_id_event_at
    ON shadow_order_events (shadow_order_id, event_at ASC);

CREATE TABLE IF NOT EXISTS shadow_positions (
    id UUID PRIMARY KEY,
    shadow_run_id UUID NOT NULL REFERENCES shadow_runs(id) ON DELETE CASCADE,
    shadow_order_id UUID NOT NULL REFERENCES shadow_orders(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    intended_outcome TEXT NULL,
    size NUMERIC(18, 6) NOT NULL DEFAULT 0,
    avg_entry NUMERIC(10, 6) NULL,
    current_status TEXT NOT NULL,
    mark_price NUMERIC(10, 6) NULL,
    unrealized NUMERIC(18, 6) NULL,
    realized NUMERIC(18, 6) NULL,
    thesis_state TEXT NOT NULL,
    invalidation_state TEXT NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_shadow_positions_run_status_updated_at
    ON shadow_positions (shadow_run_id, current_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS shadow_position_events (
    id UUID PRIMARY KEY,
    shadow_position_id UUID NOT NULL REFERENCES shadow_positions(id) ON DELETE CASCADE,
    event_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shadow_position_events_position_id_event_at
    ON shadow_position_events (shadow_position_id, event_at ASC);
