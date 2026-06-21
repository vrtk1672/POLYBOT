ALTER TABLE paper_capital_ledger
    DROP CONSTRAINT IF EXISTS paper_capital_ledger_event_type_check;

ALTER TABLE paper_capital_ledger
    ADD CONSTRAINT paper_capital_ledger_event_type_check CHECK (
        event_type IN (
            'ACCOUNT_INITIALIZED',
            'CAPITAL_LOCKED_ON_FILL',
            'CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL',
            'CAPITAL_RELEASED_ON_CLOSE',
            'CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE',
            'REALIZED_PNL_APPLIED',
            'REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE',
            'UNREALIZED_PNL_MARK',
            'DAILY_LOSS_GUARD_TRIGGERED',
            'RISK_LIMIT_BLOCK',
            'INSUFFICIENT_BALANCE_BLOCK',
            'MAX_OPEN_POSITIONS_BLOCK',
            'MAX_EXPOSURE_BLOCK',
            'RECONCILIATION_CHECK'
        )
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_capital_backfill_release_close
    ON paper_capital_ledger (account_id, paper_close_id)
    WHERE event_type = 'CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE'
      AND paper_close_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_capital_backfill_realized_close
    ON paper_capital_ledger (account_id, paper_close_id)
    WHERE event_type = 'REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE'
      AND paper_close_id IS NOT NULL;
