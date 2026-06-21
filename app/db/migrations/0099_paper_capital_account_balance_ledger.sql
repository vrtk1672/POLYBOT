CREATE TABLE IF NOT EXISTS paper_accounts (
    id BIGSERIAL PRIMARY KEY,
    account_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    initial_balance NUMERIC(18, 8) NOT NULL DEFAULT 1000.00 CHECK (initial_balance >= 0),
    current_balance NUMERIC(18, 8) NOT NULL DEFAULT 1000.00,
    available_balance NUMERIC(18, 8) NOT NULL DEFAULT 1000.00,
    locked_balance NUMERIC(18, 8) NOT NULL DEFAULT 0,
    open_exposure NUMERIC(18, 8) NOT NULL DEFAULT 0,
    realized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    daily_pnl NUMERIC(18, 8) NOT NULL DEFAULT 0,
    risk_per_trade_pct NUMERIC(10, 6) NOT NULL DEFAULT 1.0,
    max_position_size NUMERIC(18, 8) NOT NULL DEFAULT 25.00,
    max_daily_loss_pct NUMERIC(10, 6) NOT NULL DEFAULT 5.0,
    max_open_positions INTEGER NOT NULL DEFAULT 3 CHECK (max_open_positions >= 0),
    max_total_open_exposure_pct NUMERIC(10, 6) NOT NULL DEFAULT 15.0,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT paper_accounts_balance_nonnegative CHECK (
        current_balance >= 0
        AND available_balance >= 0
        AND locked_balance >= 0
        AND open_exposure >= 0
    )
);

CREATE INDEX IF NOT EXISTS idx_paper_accounts_status
    ON paper_accounts (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS paper_capital_ledger (
    id BIGSERIAL PRIMARY KEY,
    ledger_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL REFERENCES paper_accounts(account_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NULL,
    paper_intent_id TEXT NULL,
    paper_order_id TEXT NULL,
    paper_fill_id TEXT NULL,
    paper_position_id TEXT NULL,
    paper_close_id TEXT NULL,
    amount NUMERIC(18, 8) NOT NULL DEFAULT 0,
    balance_before NUMERIC(18, 8) NOT NULL,
    balance_after NUMERIC(18, 8) NOT NULL,
    available_before NUMERIC(18, 8) NOT NULL,
    available_after NUMERIC(18, 8) NOT NULL,
    locked_before NUMERIC(18, 8) NOT NULL,
    locked_after NUMERIC(18, 8) NOT NULL,
    realized_pnl_delta NUMERIC(18, 8) NOT NULL DEFAULT 0,
    unrealized_pnl_snapshot NUMERIC(18, 8) NULL,
    reason TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT paper_capital_ledger_event_type_check CHECK (
        event_type IN (
            'ACCOUNT_INITIALIZED',
            'CAPITAL_LOCKED_ON_FILL',
            'CAPITAL_RELEASED_ON_CLOSE',
            'REALIZED_PNL_APPLIED',
            'UNREALIZED_PNL_MARK',
            'DAILY_LOSS_GUARD_TRIGGERED',
            'RISK_LIMIT_BLOCK',
            'INSUFFICIENT_BALANCE_BLOCK',
            'MAX_OPEN_POSITIONS_BLOCK',
            'MAX_EXPOSURE_BLOCK',
            'RECONCILIATION_CHECK'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_capital_lock_fill
    ON paper_capital_ledger (account_id, paper_fill_id)
    WHERE event_type = 'CAPITAL_LOCKED_ON_FILL' AND paper_fill_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_capital_release_close
    ON paper_capital_ledger (account_id, paper_close_id)
    WHERE event_type = 'CAPITAL_RELEASED_ON_CLOSE' AND paper_close_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_capital_realized_close
    ON paper_capital_ledger (account_id, paper_close_id)
    WHERE event_type = 'REALIZED_PNL_APPLIED' AND paper_close_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_paper_capital_ledger_account_created
    ON paper_capital_ledger (account_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_capital_ledger_position
    ON paper_capital_ledger (paper_position_id)
    WHERE paper_position_id IS NOT NULL;

INSERT INTO paper_accounts (
    account_id, name, currency, initial_balance, current_balance,
    available_balance, locked_balance, open_exposure, realized_pnl,
    unrealized_pnl, daily_pnl, risk_per_trade_pct, max_position_size,
    max_daily_loss_pct, max_open_positions, max_total_open_exposure_pct,
    status, metadata_json, created_at, updated_at
)
VALUES (
    'paper_default', 'Default Paper Account', 'USD', 1000.00, 1000.00,
    1000.00, 0, 0, 0, 0, 0, 1.0, 25.00, 5.0, 3, 15.0,
    'ACTIVE', '{"paper_only": true, "source": "0099_paper_capital_account_balance_ledger"}'::jsonb,
    now(), now()
)
ON CONFLICT (account_id) DO NOTHING;

INSERT INTO paper_capital_ledger (
    ledger_id, account_id, event_type, source_type, source_id,
    amount, balance_before, balance_after, available_before,
    available_after, locked_before, locked_after, realized_pnl_delta,
    unrealized_pnl_snapshot, reason, metadata_json, created_at
)
SELECT
    'paper_capital_default_initialized',
    account_id,
    'ACCOUNT_INITIALIZED',
    'MIGRATION',
    '0099_paper_capital_account_balance_ledger',
    initial_balance,
    0,
    current_balance,
    0,
    available_balance,
    0,
    locked_balance,
    0,
    unrealized_pnl,
    'DEFAULT_PAPER_ACCOUNT_INITIALIZED',
    '{"paper_only": true}'::jsonb,
    now()
FROM paper_accounts
WHERE account_id = 'paper_default'
ON CONFLICT (ledger_id) DO NOTHING;
