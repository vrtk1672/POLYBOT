CREATE TABLE IF NOT EXISTS whale_scan_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    scanner_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_scan_runs_started_at
    ON whale_scan_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS whale_events (
    id UUID PRIMARY KEY,
    whale_scan_run_id UUID NOT NULL REFERENCES whale_scan_runs(id) ON DELETE CASCADE,
    wallet_address TEXT NOT NULL,
    market_id TEXT NOT NULL,
    event_timestamp TIMESTAMPTZ NOT NULL,
    event_direction_class TEXT NOT NULL CHECK (
        event_direction_class IN ('ENTRY', 'EXIT', 'REVERSAL_CANDIDATE', 'UNKNOWN')
    ),
    side_or_outcome TEXT NULL,
    size NUMERIC(18, 6) NOT NULL,
    notional NUMERIC(18, 6) NULL,
    price NUMERIC(18, 6) NULL,
    transaction_ref TEXT NULL,
    source_type TEXT NOT NULL,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    detection_reason_code TEXT NOT NULL,
    detection_reason_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_events_run_id
    ON whale_events (whale_scan_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_whale_events_wallet
    ON whale_events (wallet_address, event_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_whale_events_market
    ON whale_events (market_id, event_timestamp DESC);

CREATE TABLE IF NOT EXISTS whale_registry (
    id UUID PRIMARY KEY,
    wallet_address TEXT NOT NULL UNIQUE,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    total_events INTEGER NOT NULL DEFAULT 0,
    last_market_id TEXT NULL,
    last_event_direction_class TEXT NULL CHECK (
        last_event_direction_class IN ('ENTRY', 'EXIT', 'REVERSAL_CANDIDATE', 'UNKNOWN')
    ),
    registry_status TEXT NOT NULL CHECK (
        registry_status IN ('ACTIVE', 'WATCHLIST', 'DORMANT', 'IGNORE')
    ),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_registry_last_seen
    ON whale_registry (last_seen_at DESC);
