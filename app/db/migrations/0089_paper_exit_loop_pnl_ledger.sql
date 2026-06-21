CREATE TABLE IF NOT EXISTS paper_position_closes (
    id BIGSERIAL PRIMARY KEY,
    close_id TEXT NOT NULL UNIQUE,
    position_id UUID NOT NULL REFERENCES paper_positions(id) ON DELETE CASCADE,
    trade_id TEXT NULL,
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price NUMERIC(18, 8) NOT NULL,
    exit_price NUMERIC(18, 8) NOT NULL,
    quantity NUMERIC(18, 8) NOT NULL CHECK (quantity > 0),
    realized_pnl NUMERIC(18, 8) NOT NULL,
    realized_pnl_pct NUMERIC(18, 8) NULL,
    exit_reason TEXT NOT NULL,
    price_basis TEXT NOT NULL,
    source_exit_price TEXT NOT NULL,
    exit_plan_id TEXT NULL,
    risk_decision_id TEXT NULL,
    correlation_id TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT paper_position_closes_reason_check CHECK (
        exit_reason IN (
            'TAKE_PROFIT',
            'STOP_LOSS',
            'MAX_HOLD_TIME',
            'EXIT_PLAN_TRIGGERED',
            'RISK_INVALIDATION',
            'MANUAL_PAPER_CLOSE'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_position_closes_position
    ON paper_position_closes (position_id);

CREATE INDEX IF NOT EXISTS idx_paper_position_closes_market_created
    ON paper_position_closes (market_id, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_trade_ledger (
    id BIGSERIAL PRIMARY KEY,
    ledger_id TEXT NOT NULL UNIQUE,
    position_id UUID NOT NULL REFERENCES paper_positions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('OPEN', 'MARK', 'CLOSE')),
    market_id TEXT NOT NULL,
    side TEXT NOT NULL,
    amount NUMERIC(18, 8) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18, 8) NULL,
    unrealized_pnl NUMERIC(18, 8) NULL,
    reason TEXT NOT NULL,
    correlation_id TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_trade_ledger_position_close
    ON paper_trade_ledger (position_id, event_type)
    WHERE event_type = 'CLOSE';

CREATE INDEX IF NOT EXISTS idx_paper_trade_ledger_market_created
    ON paper_trade_ledger (market_id, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_daily_pnl (
    id BIGSERIAL PRIMARY KEY,
    pnl_date DATE NOT NULL UNIQUE,
    realized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(18, 8) NULL,
    net_pnl NUMERIC(18, 8) NULL,
    gross_profit NUMERIC(18, 8) NOT NULL DEFAULT 0,
    gross_loss NUMERIC(18, 8) NOT NULL DEFAULT 0,
    closed_trades_count INTEGER NOT NULL DEFAULT 0 CHECK (closed_trades_count >= 0),
    open_positions_count INTEGER NOT NULL DEFAULT 0 CHECK (open_positions_count >= 0),
    winning_trades_count INTEGER NOT NULL DEFAULT 0 CHECK (winning_trades_count >= 0),
    losing_trades_count INTEGER NOT NULL DEFAULT 0 CHECK (losing_trades_count >= 0),
    stale_price_count INTEGER NOT NULL DEFAULT 0 CHECK (stale_price_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_daily_pnl_updated
    ON paper_daily_pnl (updated_at DESC);

CREATE TABLE IF NOT EXISTS paper_exit_loop_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    system_power TEXT NOT NULL DEFAULT 'ON',
    status TEXT NOT NULL,
    open_positions_checked INTEGER NOT NULL DEFAULT 0,
    closed_positions_count INTEGER NOT NULL DEFAULT 0,
    marked_positions_count INTEGER NOT NULL DEFAULT 0,
    blocked_positions_count INTEGER NOT NULL DEFAULT 0,
    no_exit_price_count INTEGER NOT NULL DEFAULT 0,
    no_exit_condition_count INTEGER NOT NULL DEFAULT 0,
    duplicate_close_skipped_count INTEGER NOT NULL DEFAULT 0,
    orphan_positions_count INTEGER NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(18, 8) NULL,
    paper_orders_delta INTEGER NOT NULL DEFAULT 0,
    paper_positions_delta INTEGER NOT NULL DEFAULT 0,
    real_orders_delta INTEGER NOT NULL DEFAULT 0,
    fills_delta INTEGER NOT NULL DEFAULT 0,
    live_orders_delta INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT paper_exit_loop_runs_status_check CHECK (status IN ('OK', 'NO_OPEN_PAPER_POSITIONS', 'BLOCKED', 'DEGRADED', 'ERROR'))
);

CREATE INDEX IF NOT EXISTS idx_paper_exit_loop_runs_created
    ON paper_exit_loop_runs (created_at DESC);
