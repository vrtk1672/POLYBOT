CREATE TABLE IF NOT EXISTS markets_v2 (
    id BIGSERIAL PRIMARY KEY,
    market_id TEXT NOT NULL UNIQUE,
    condition_id TEXT NULL,
    question TEXT NOT NULL,
    slug TEXT NULL,
    category TEXT NULL,
    market_family TEXT NULL,
    yes_token_id TEXT NULL,
    no_token_id TEXT NULL,
    outcome_tokens_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source TEXT NOT NULL DEFAULT 'polymarket',
    resolution_source TEXT NULL,
    accepting_orders BOOLEAN NULL,
    closed BOOLEAN NOT NULL DEFAULT false,
    archived BOOLEAN NOT NULL DEFAULT false,
    active BOOLEAN NOT NULL DEFAULT true,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    close_time TIMESTAMPTZ NULL,
    resolution_time TIMESTAMPTZ NULL,
    raw_market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_markets_v2_condition_id ON markets_v2 (condition_id);
CREATE INDEX IF NOT EXISTS idx_markets_v2_slug ON markets_v2 (slug);
CREATE INDEX IF NOT EXISTS idx_markets_v2_category ON markets_v2 (category);
CREATE INDEX IF NOT EXISTS idx_markets_v2_market_family ON markets_v2 (market_family);
CREATE INDEX IF NOT EXISTS idx_markets_v2_active ON markets_v2 (active);
CREATE INDEX IF NOT EXISTS idx_markets_v2_closed ON markets_v2 (closed);
CREATE INDEX IF NOT EXISTS idx_markets_v2_accepting_orders ON markets_v2 (accepting_orders);
CREATE INDEX IF NOT EXISTS idx_markets_v2_close_time ON markets_v2 (close_time);

CREATE TABLE IF NOT EXISTS market_rules (
    id BIGSERIAL PRIMARY KEY,
    market_id TEXT NOT NULL UNIQUE,
    rules_text TEXT NULL,
    resolution_source TEXT NULL,
    resolution_source_url TEXT NULL,
    settlement_method TEXT NULL,
    deadline_at TIMESTAMPTZ NULL,
    rules_hash TEXT NULL,
    ambiguity_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_rules_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_rules_market_id ON market_rules (market_id);
CREATE INDEX IF NOT EXISTS idx_market_rules_rules_hash ON market_rules (rules_hash);
CREATE INDEX IF NOT EXISTS idx_market_rules_deadline_at ON market_rules (deadline_at);

CREATE TABLE IF NOT EXISTS market_snapshots_v2 (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    cycle_id TEXT NULL,
    correlation_id TEXT NULL,
    current_price_yes NUMERIC NULL,
    current_price_no NUMERIC NULL,
    best_bid NUMERIC NULL,
    best_ask NUMERIC NULL,
    spread NUMERIC NULL,
    volume_1h NUMERIC NULL,
    volume_24h NUMERIC NULL,
    liquidity NUMERIC NULL,
    time_to_close_seconds INTEGER NULL,
    accepting_orders BOOLEAN NULL,
    closed BOOLEAN NULL,
    data_completeness_score NUMERIC NOT NULL DEFAULT 0,
    stale BOOLEAN NOT NULL DEFAULT false,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_v2_market_time ON market_snapshots_v2 (market_id, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_v2_cycle_id ON market_snapshots_v2 (cycle_id);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_v2_correlation_id ON market_snapshots_v2 (correlation_id);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_v2_stale ON market_snapshots_v2 (stale);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_v2_completeness ON market_snapshots_v2 (data_completeness_score);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id BIGSERIAL PRIMARY KEY,
    orderbook_snapshot_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    token_id TEXT NULL,
    side TEXT NULL,
    best_bid NUMERIC NULL,
    best_ask NUMERIC NULL,
    spread NUMERIC NULL,
    mid_price NUMERIC NULL,
    depth_1c NUMERIC NULL,
    depth_2c NUMERIC NULL,
    depth_5c NUMERIC NULL,
    bid_depth_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ask_depth_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    imbalance NUMERIC NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_orderbook_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_market_time ON orderbook_snapshots (market_id, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_token_id ON orderbook_snapshots (token_id);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_spread ON orderbook_snapshots (spread);
CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_depth_2c ON orderbook_snapshots (depth_2c);

CREATE TABLE IF NOT EXISTS liquidity_snapshots (
    id BIGSERIAL PRIMARY KEY,
    liquidity_snapshot_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    orderbook_snapshot_id TEXT NULL,
    liquidity_score NUMERIC NOT NULL DEFAULT 0,
    exit_quality NUMERIC NOT NULL DEFAULT 0,
    expected_slippage_small NUMERIC NULL,
    expected_slippage_medium NUMERIC NULL,
    expected_slippage_large NUMERIC NULL,
    max_safe_size NUMERIC NULL,
    fill_probability NUMERIC NULL,
    liquidity_usd NUMERIC NULL,
    depth_1c NUMERIC NULL,
    depth_2c NUMERIC NULL,
    depth_5c NUMERIC NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_liquidity_snapshots_market_time ON liquidity_snapshots (market_id, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_liquidity_snapshots_score ON liquidity_snapshots (liquidity_score);
CREATE INDEX IF NOT EXISTS idx_liquidity_snapshots_exit_quality ON liquidity_snapshots (exit_quality);
CREATE INDEX IF NOT EXISTS idx_liquidity_snapshots_max_safe_size ON liquidity_snapshots (max_safe_size);

CREATE TABLE IF NOT EXISTS fee_snapshots (
    id BIGSERIAL PRIMARY KEY,
    fee_snapshot_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    maker_fee NUMERIC NULL,
    taker_fee NUMERIC NULL,
    spread_cost NUMERIC NULL,
    estimated_slippage_cost NUMERIC NULL,
    reward_pool NUMERIC NULL,
    reward_rate NUMERIC NULL,
    net_edge_adjustment NUMERIC NULL,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_fee_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_fee_snapshots_market_time ON fee_snapshots (market_id, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS market_lifecycle_events (
    id BIGSERIAL PRIMARY KEY,
    lifecycle_event_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    previous_status TEXT NULL,
    new_status TEXT NULL,
    event_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_service TEXT NOT NULL,
    correlation_id TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT market_lifecycle_event_type_chk CHECK (event_type IN ('DISCOVERED', 'UPDATED', 'OPENED', 'PAUSED', 'CLOSED', 'RESOLVED', 'ARCHIVED', 'STALE', 'REACTIVATED'))
);

CREATE INDEX IF NOT EXISTS idx_market_lifecycle_events_market_time ON market_lifecycle_events (market_id, event_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_lifecycle_events_event_type ON market_lifecycle_events (event_type);
CREATE INDEX IF NOT EXISTS idx_market_lifecycle_events_correlation_id ON market_lifecycle_events (correlation_id);

CREATE TABLE IF NOT EXISTS market_family_map (
    id BIGSERIAL PRIMARY KEY,
    market_id TEXT NOT NULL UNIQUE,
    market_family TEXT NOT NULL,
    category TEXT NULL,
    subcategory TEXT NULL,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    classifier_version TEXT NOT NULL DEFAULT 'v2.2_rule_based',
    confidence NUMERIC NOT NULL DEFAULT 0,
    reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_market_family_map_family ON market_family_map (market_family);
CREATE INDEX IF NOT EXISTS idx_market_family_map_category ON market_family_map (category);
CREATE INDEX IF NOT EXISTS idx_market_family_map_confidence ON market_family_map (confidence);
