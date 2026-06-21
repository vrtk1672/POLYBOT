CREATE TABLE IF NOT EXISTS paper_runs (
    id UUID PRIMARY KEY,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    mode TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    markets_seen_count INTEGER NOT NULL DEFAULT 0,
    markets_ranked_count INTEGER NOT NULL DEFAULT 0,
    candidates_selected_count INTEGER NOT NULL DEFAULT 0,
    signals_emitted_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_runs_cycle_id_created_at
    ON paper_runs (cycle_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_runs_status_created_at
    ON paper_runs (status, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_signals (
    id UUID PRIMARY KEY,
    paper_run_id UUID NOT NULL REFERENCES paper_runs(id) ON DELETE CASCADE,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    market_id TEXT NOT NULL,
    decision_id UUID NULL REFERENCES decision_ledger(id) ON DELETE SET NULL,
    signal_type TEXT NOT NULL CHECK (signal_type IN ('WOULD_ENTER', 'WOULD_SKIP', 'WOULD_BLOCK', 'NO_ACTION')),
    intended_outcome TEXT NULL,
    trade_type TEXT NULL,
    bucket_type TEXT NULL,
    confidence NUMERIC(10, 6) NULL,
    expected_edge_proxy NUMERIC(10, 4) NULL,
    intended_price NUMERIC(10, 6) NULL,
    intended_size NUMERIC(18, 6) NULL,
    guard_result TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_text TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (paper_run_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_signals_run_id_created_at
    ON paper_signals (paper_run_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_paper_signals_cycle_id_market_id
    ON paper_signals (cycle_id, market_id);
