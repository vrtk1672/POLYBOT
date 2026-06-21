CREATE TABLE IF NOT EXISTS paper_sessions (
    id BIGSERIAL PRIMARY KEY,
    paper_session_id TEXT NOT NULL UNIQUE,
    session_name TEXT NOT NULL,
    starting_balance NUMERIC NOT NULL DEFAULT 0,
    current_balance_snapshot NUMERIC NOT NULL DEFAULT 0,
    realized_pnl NUMERIC NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC NOT NULL DEFAULT 0,
    net_pnl NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    closed_reason TEXT,
    reset_report_path TEXT,
    created_by TEXT NOT NULL DEFAULT 'system',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_sessions_one_active ON paper_sessions (status) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_paper_sessions_started ON paper_sessions (started_at DESC);

CREATE TABLE IF NOT EXISTS paper_session_resets (
    id BIGSERIAL PRIMARY KEY,
    reset_id TEXT NOT NULL UNIQUE,
    previous_session_id TEXT,
    new_session_id TEXT,
    requested_balance NUMERIC NOT NULL,
    status TEXT NOT NULL,
    report_dir TEXT,
    previous_intents_count INTEGER NOT NULL DEFAULT 0,
    previous_orders_count INTEGER NOT NULL DEFAULT 0,
    previous_fills_count INTEGER NOT NULL DEFAULT 0,
    previous_positions_count INTEGER NOT NULL DEFAULT 0,
    previous_open_positions_count INTEGER NOT NULL DEFAULT 0,
    previous_realized_pnl NUMERIC NOT NULL DEFAULT 0,
    previous_unrealized_pnl NUMERIC NOT NULL DEFAULT 0,
    previous_net_pnl NUMERIC NOT NULL DEFAULT 0,
    reset_started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reset_completed_at TIMESTAMPTZ,
    errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by TEXT NOT NULL DEFAULT 'system',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_session_resets_created ON paper_session_resets (reset_started_at DESC);

ALTER TABLE paper_intents ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_intents ADD COLUMN IF NOT EXISTS reset_id TEXT;
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_orders ADD COLUMN IF NOT EXISTS reset_id TEXT;
ALTER TABLE paper_fills ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_fills ADD COLUMN IF NOT EXISTS reset_id TEXT;
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS reset_id TEXT;
ALTER TABLE paper_position_closes ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_position_closes ADD COLUMN IF NOT EXISTS reset_id TEXT;
ALTER TABLE paper_daily_pnl ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_daily_pnl ADD COLUMN IF NOT EXISTS reset_id TEXT;
ALTER TABLE paper_capital_ledger ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_capital_ledger ADD COLUMN IF NOT EXISTS reset_id TEXT;
ALTER TABLE paper_accounts ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_runs ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_signals ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_trade_ledger ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_order_events ADD COLUMN IF NOT EXISTS paper_session_id TEXT;
ALTER TABLE paper_position_events ADD COLUMN IF NOT EXISTS paper_session_id TEXT;

ALTER TABLE paper_position_closes DROP CONSTRAINT IF EXISTS paper_position_closes_reason_check;
ALTER TABLE paper_position_closes ADD CONSTRAINT paper_position_closes_reason_check CHECK (exit_reason IN ('TAKE_PROFIT','STOP_LOSS','MAX_HOLD_TIME','EXIT_PLAN_TRIGGERED','RISK_INVALIDATION','MANUAL_PAPER_CLOSE','RESET_CLOSED','RESET_ARCHIVED'));

ALTER TABLE paper_intents DROP CONSTRAINT IF EXISTS paper_intents_intent_status_check;
ALTER TABLE paper_intents ADD CONSTRAINT paper_intents_intent_status_check CHECK (intent_status IN ('CREATED','READY','EXECUTING','EXECUTED','POSITION_OPENED','CLOSED','BLOCKED','CANCELLED','ERROR','EXPIRED','RESET_ARCHIVED','RESET_CLOSED'));

ALTER TABLE paper_daily_pnl DROP CONSTRAINT IF EXISTS paper_daily_pnl_pnl_date_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_daily_pnl_session_date ON paper_daily_pnl (paper_session_id, pnl_date);

CREATE INDEX IF NOT EXISTS idx_paper_intents_session ON paper_intents (paper_session_id);
CREATE INDEX IF NOT EXISTS idx_paper_orders_session ON paper_orders (paper_session_id);
CREATE INDEX IF NOT EXISTS idx_paper_fills_session ON paper_fills (paper_session_id);
CREATE INDEX IF NOT EXISTS idx_paper_positions_session ON paper_positions (paper_session_id);
CREATE INDEX IF NOT EXISTS idx_paper_position_closes_session ON paper_position_closes (paper_session_id);
CREATE INDEX IF NOT EXISTS idx_paper_capital_ledger_session ON paper_capital_ledger (paper_session_id);
