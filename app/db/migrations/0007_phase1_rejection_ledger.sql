CREATE TABLE IF NOT EXISTS rejection_ledger (
    id UUID PRIMARY KEY,
    cycle_id UUID NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cycle_id, market_id, stage, reason_code)
);

CREATE INDEX IF NOT EXISTS idx_rejection_ledger_cycle_id_created_at
    ON rejection_ledger (cycle_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_rejection_ledger_market_id_created_at
    ON rejection_ledger (market_id, created_at DESC);
