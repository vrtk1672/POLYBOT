ALTER TABLE neural_events
    DROP CONSTRAINT IF EXISTS neural_events_source_type_chk;

ALTER TABLE neural_events
    ADD CONSTRAINT neural_events_source_type_chk CHECK (
        source_type IN (
            'neuron',
            'brain',
            'risk',
            'exit',
            'eligibility',
            'paper',
            'capital',
            'memory',
            'market',
            'runtime',
            'system',
            'CLOB_READ_ONLY'
        )
    );

CREATE TABLE IF NOT EXISTS live_orderbook_watchlist (
    id BIGSERIAL PRIMARY KEY,
    watch_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    side TEXT NOT NULL,
    token_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    last_polled_at TIMESTAMPTZ NULL,
    last_success_at TIMESTAMPTZ NULL,
    last_failure_at TIMESTAMPTZ NULL,
    last_snapshot_id BIGINT NULL,
    last_best_bid NUMERIC NULL,
    last_best_ask NUMERIC NULL,
    last_spread NUMERIC NULL,
    last_liquidity_score NUMERIC NULL,
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_orderbook_watchlist_side_check CHECK (side IN ('YES', 'NO')),
    CONSTRAINT live_orderbook_watchlist_priority_check CHECK (priority BETWEEN 1 AND 10),
    CONSTRAINT live_orderbook_watchlist_status_check CHECK (status IN ('ACTIVE', 'DEGRADED', 'TOKEN_UNAVAILABLE', 'MARKET_RESOLVED', 'DISABLED'))
);

CREATE INDEX IF NOT EXISTS idx_live_orderbook_watchlist_status_priority
    ON live_orderbook_watchlist (status, priority, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_live_orderbook_watchlist_market
    ON live_orderbook_watchlist (market_id, side);

CREATE TABLE IF NOT EXISTS live_orderbook_watcher_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    system_power TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT false,
    watch_items_checked INTEGER NOT NULL DEFAULT 0 CHECK (watch_items_checked >= 0),
    orderbooks_refreshed INTEGER NOT NULL DEFAULT 0 CHECK (orderbooks_refreshed >= 0),
    spread_changed_count INTEGER NOT NULL DEFAULT 0 CHECK (spread_changed_count >= 0),
    liquidity_changed_count INTEGER NOT NULL DEFAULT 0 CHECK (liquidity_changed_count >= 0),
    token_unavailable_count INTEGER NOT NULL DEFAULT 0 CHECK (token_unavailable_count >= 0),
    market_resolved_count INTEGER NOT NULL DEFAULT 0 CHECK (market_resolved_count >= 0),
    events_published INTEGER NOT NULL DEFAULT 0 CHECK (events_published >= 0),
    snapshots_created INTEGER NOT NULL DEFAULT 0 CHECK (snapshots_created >= 0),
    errors_count INTEGER NOT NULL DEFAULT 0 CHECK (errors_count >= 0),
    blocker_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_orderbook_watcher_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_live_orderbook_watcher_runs_created
    ON live_orderbook_watcher_runs (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS live_orderbook_watcher_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    watch_id TEXT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    clob_status TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED',
    previous_snapshot_id BIGINT NULL,
    new_snapshot_id BIGINT NULL,
    previous_best_bid NUMERIC NULL,
    new_best_bid NUMERIC NULL,
    previous_best_ask NUMERIC NULL,
    new_best_ask NUMERIC NULL,
    previous_spread NUMERIC NULL,
    new_spread NUMERIC NULL,
    previous_liquidity_score NUMERIC NULL,
    new_liquidity_score NUMERIC NULL,
    spread_delta NUMERIC NULL,
    liquidity_delta NUMERIC NULL,
    events_published_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT live_orderbook_watcher_trace_side_check CHECK (side IS NULL OR side IN ('YES', 'NO'))
);

CREATE INDEX IF NOT EXISTS idx_live_orderbook_watcher_traces_run
    ON live_orderbook_watcher_traces (run_id, id);

CREATE INDEX IF NOT EXISTS idx_live_orderbook_watcher_traces_market
    ON live_orderbook_watcher_traces (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;
