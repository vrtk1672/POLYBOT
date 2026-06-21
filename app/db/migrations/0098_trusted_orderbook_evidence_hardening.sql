CREATE TABLE IF NOT EXISTS trusted_orderbook_evidence_links (
    id BIGSERIAL PRIMARY KEY,
    link_id TEXT NOT NULL UNIQUE,
    candidate_id TEXT NOT NULL,
    market_id TEXT NULL,
    side TEXT NULL,
    expected_token_id TEXT NULL,
    orderbook_snapshot_id BIGINT NULL,
    orderbook_snapshot_ref TEXT NULL,
    orderbook_token_id TEXT NULL,
    trusted BOOLEAN NOT NULL DEFAULT false,
    trust_status TEXT NOT NULL,
    trust_reason TEXT NOT NULL,
    best_bid NUMERIC NULL,
    best_ask NUMERIC NULL,
    mid_price NUMERIC NULL,
    spread NUMERIC NULL,
    liquidity_score NUMERIC NULL,
    age_seconds NUMERIC NULL,
    freshness_threshold_seconds INTEGER NOT NULL DEFAULT 180,
    signal_market_link_id BIGINT NULL,
    neuron_signal_binding_id BIGINT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT trusted_orderbook_candidate_unique UNIQUE (candidate_id),
    CONSTRAINT trusted_orderbook_side_check CHECK (side IS NULL OR side IN ('YES', 'NO')),
    CONSTRAINT trusted_orderbook_status_check CHECK (trust_status IN ('TRUSTED', 'REJECTED', 'BLOCKED'))
);

CREATE OR REPLACE FUNCTION _jsonb_without_codes(values_json JSONB, codes TEXT[])
RETURNS JSONB
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT COALESCE(jsonb_agg(item), '[]'::jsonb)
    FROM jsonb_array_elements_text(COALESCE(values_json, '[]'::jsonb)) AS item
    WHERE NOT (item = ANY(codes))
$$;

CREATE INDEX IF NOT EXISTS idx_trusted_orderbook_links_market
    ON trusted_orderbook_evidence_links (market_id, side, trusted);

CREATE INDEX IF NOT EXISTS idx_trusted_orderbook_links_snapshot
    ON trusted_orderbook_evidence_links (orderbook_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_trusted_orderbook_links_updated
    ON trusted_orderbook_evidence_links (updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS trusted_orderbook_evidence_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL DEFAULT 'ON',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    candidates_checked INTEGER NOT NULL DEFAULT 0,
    candidates_with_side INTEGER NOT NULL DEFAULT 0,
    candidates_with_trusted_binding INTEGER NOT NULL DEFAULT 0,
    candidates_with_orderbook INTEGER NOT NULL DEFAULT 0,
    trusted_matches_created INTEGER NOT NULL DEFAULT 0,
    trusted_matches_refreshed INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    missing_orderbook_count INTEGER NOT NULL DEFAULT 0,
    stale_count INTEGER NOT NULL DEFAULT 0,
    token_mismatch_count INTEGER NOT NULL DEFAULT 0,
    missing_mid_price_count INTEGER NOT NULL DEFAULT 0,
    spread_too_wide_count INTEGER NOT NULL DEFAULT 0,
    liquidity_too_low_count INTEGER NOT NULL DEFAULT 0,
    missing_trusted_orderbook_before INTEGER NOT NULL DEFAULT 0,
    missing_trusted_orderbook_after INTEGER NOT NULL DEFAULT 0,
    missing_fresh_orderbook_before INTEGER NOT NULL DEFAULT 0,
    missing_fresh_orderbook_after INTEGER NOT NULL DEFAULT 0,
    live_orders_delta INTEGER NOT NULL DEFAULT 0,
    real_orders_delta INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT trusted_orderbook_run_power_check CHECK (system_power IN ('ON', 'OFF'))
);

CREATE INDEX IF NOT EXISTS idx_trusted_orderbook_runs_cycle
    ON trusted_orderbook_evidence_runs (cycle_id);

CREATE INDEX IF NOT EXISTS idx_trusted_orderbook_runs_created
    ON trusted_orderbook_evidence_runs (created_at DESC, id DESC);
