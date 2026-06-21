CREATE TABLE IF NOT EXISTS decision_ledger (
    id UUID PRIMARY KEY,
    cycle_id UUID NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
    market_snapshot_id BIGINT NOT NULL REFERENCES market_snapshots(id) ON DELETE CASCADE,
    ranking_snapshot_id BIGINT NULL REFERENCES ranking_snapshots(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    decision_type TEXT NOT NULL CHECK (decision_type IN ('SELECT', 'SKIP', 'BLOCK', 'NO_ACTION')),
    selected BOOLEAN NOT NULL DEFAULT FALSE,
    reason TEXT NOT NULL,
    confidence NUMERIC(10, 6) NULL,
    trade_type TEXT NULL,
    bucket_type TEXT NULL,
    expected_edge_proxy NUMERIC(10, 4) NULL,
    invalidation_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (cycle_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_decision_ledger_cycle_id ON decision_ledger (cycle_id);
CREATE INDEX IF NOT EXISTS idx_decision_ledger_market_id_created_at
    ON decision_ledger (market_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decision_ledger_selected_created_at
    ON decision_ledger (selected, created_at DESC);
