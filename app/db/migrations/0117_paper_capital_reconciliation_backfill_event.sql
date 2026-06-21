ALTER TABLE paper_capital_ledger
    DROP CONSTRAINT IF EXISTS paper_capital_ledger_event_type_check;

ALTER TABLE paper_capital_ledger
    ADD CONSTRAINT paper_capital_ledger_event_type_check CHECK (
        event_type IN (
            'ACCOUNT_INITIALIZED',
            'CAPITAL_LOCKED_ON_FILL',
            'CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL',
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
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_capital_backfill_lock_fill
    ON paper_capital_ledger (account_id, paper_fill_id)
    WHERE event_type = 'CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL'
      AND paper_fill_id IS NOT NULL;
