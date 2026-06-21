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
            'CLOB_READ_ONLY',
            'PAPER_POSITION'
        )
    );

ALTER TABLE position_reactions
    DROP CONSTRAINT IF EXISTS position_reactions_type_chk;

ALTER TABLE position_reactions
    ADD CONSTRAINT position_reactions_type_chk CHECK (reaction_type IN (
        'ADVERSE_NEWS',
        'POSITIVE_NEWS',
        'WHALE_ENTRY',
        'WHALE_EXIT',
        'LIQUIDITY_DROP',
        'LIQUIDITY_IMPROVED',
        'SPREAD_WIDENED',
        'SPREAD_IMPROVED',
        'RISK_INCREASED',
        'RISK_DECREASED',
        'EXIT_DEGRADED',
        'EXIT_IMPROVED',
        'PNL_RISING',
        'PNL_FALLING',
        'CAPITAL_PRESSURE',
        'POSITION_AGING',
        'POSITION_ORDERBOOK_REFRESHED',
        'POSITION_EXIT_RISK',
        'TOKEN_BOOK_UNAVAILABLE_FOR_OPEN_POSITION',
        'EXIT_REVIEW',
        'HOLD_REVIEW',
        'MISSING_POSITION_TOKEN',
        'TOKEN_IDENTITY_DRIFT_REVIEW',
        'NO_REACTION'
    ));

CREATE TABLE IF NOT EXISTS position_token_locks (
    id BIGSERIAL PRIMARY KEY,
    lock_id TEXT NOT NULL UNIQUE,
    paper_position_id TEXT NOT NULL UNIQUE,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    entry_order_id TEXT NULL,
    entry_fill_id TEXT NULL,
    entry_orderbook_snapshot_id BIGINT NULL,
    source TEXT NOT NULL DEFAULT 'paper_fill_orderbook_snapshot',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_verified_at TIMESTAMPTZ NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT position_token_locks_side_chk CHECK (side IS NULL OR side IN ('YES', 'NO')),
    CONSTRAINT position_token_locks_status_chk CHECK (status IN (
        'ACTIVE',
        'MISSING_POSITION_TOKEN',
        'TOKEN_IDENTITY_DRIFT_REVIEW',
        'CLOSED',
        'DISABLED'
    ))
);

CREATE INDEX IF NOT EXISTS idx_position_token_locks_status
    ON position_token_locks (status, locked_at DESC);

CREATE INDEX IF NOT EXISTS idx_position_token_locks_token
    ON position_token_locks (token_id)
    WHERE token_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS open_position_watchdog_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    system_power TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT false,
    positions_checked INTEGER NOT NULL DEFAULT 0 CHECK (positions_checked >= 0),
    locks_created INTEGER NOT NULL DEFAULT 0 CHECK (locks_created >= 0),
    orderbooks_refreshed INTEGER NOT NULL DEFAULT 0 CHECK (orderbooks_refreshed >= 0),
    pnl_changed_count INTEGER NOT NULL DEFAULT 0 CHECK (pnl_changed_count >= 0),
    spread_widened_count INTEGER NOT NULL DEFAULT 0 CHECK (spread_widened_count >= 0),
    liquidity_dropped_count INTEGER NOT NULL DEFAULT 0 CHECK (liquidity_dropped_count >= 0),
    token_unavailable_count INTEGER NOT NULL DEFAULT 0 CHECK (token_unavailable_count >= 0),
    exit_review_count INTEGER NOT NULL DEFAULT 0 CHECK (exit_review_count >= 0),
    hold_review_count INTEGER NOT NULL DEFAULT 0 CHECK (hold_review_count >= 0),
    events_published INTEGER NOT NULL DEFAULT 0 CHECK (events_published >= 0),
    errors_count INTEGER NOT NULL DEFAULT 0 CHECK (errors_count >= 0),
    blocker_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_counts_after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    live_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (live_orders_delta >= 0),
    real_orders_delta INTEGER NOT NULL DEFAULT 0 CHECK (real_orders_delta >= 0),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT open_position_watchdog_power_chk CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_open_position_watchdog_runs_created
    ON open_position_watchdog_runs (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS open_position_watchdog_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    paper_position_id TEXT NULL,
    lock_id TEXT NULL,
    token_id TEXT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    previous_price NUMERIC NULL,
    current_price NUMERIC NULL,
    previous_pnl NUMERIC NULL,
    current_pnl NUMERIC NULL,
    previous_spread NUMERIC NULL,
    current_spread NUMERIC NULL,
    previous_liquidity_score NUMERIC NULL,
    current_liquidity_score NUMERIC NULL,
    snapshot_id BIGINT NULL,
    clob_status TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED',
    reaction_type TEXT NULL,
    severity TEXT NULL,
    event_id TEXT NULL,
    reason TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT open_position_watchdog_trace_side_chk CHECK (side IS NULL OR side IN ('YES', 'NO')),
    CONSTRAINT open_position_watchdog_trace_severity_chk CHECK (severity IS NULL OR severity IN ('INFO', 'WARN', 'CRITICAL'))
);

CREATE INDEX IF NOT EXISTS idx_open_position_watchdog_traces_run
    ON open_position_watchdog_traces (run_id, id);

CREATE INDEX IF NOT EXISTS idx_open_position_watchdog_traces_position
    ON open_position_watchdog_traces (paper_position_id, created_at DESC)
    WHERE paper_position_id IS NOT NULL;
