CREATE TABLE IF NOT EXISTS proactive_seed_mesh_adapter_payloads (
    id BIGSERIAL PRIMARY KEY,
    adapter_payload_id TEXT NOT NULL UNIQUE,
    adapter_run_id TEXT,
    seed_mesh_inquiry_id TEXT NOT NULL,
    proactive_candidate_seed_id TEXT NOT NULL,
    synthetic_candidate_id TEXT NOT NULL,
    payload_type TEXT NOT NULL DEFAULT 'PROACTIVE_SEED_RESEARCH_CANDIDATE',
    source_event_id TEXT,
    event_to_market_link_id TEXT,
    targeted_revalidation_id TEXT,
    market_memory_id TEXT,
    research_watchlist_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    side TEXT NOT NULL,
    token_id TEXT NOT NULL,
    orderbook_snapshot_id TEXT,
    link_confidence NUMERIC NOT NULL DEFAULT 0,
    direction_confidence NUMERIC NOT NULL DEFAULT 0,
    priority_score NUMERIC NOT NULL DEFAULT 0,
    research_only BOOLEAN NOT NULL DEFAULT TRUE,
    execution_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    paper_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    shadow_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    live_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_adapter_payloads_inquiry
    ON proactive_seed_mesh_adapter_payloads (seed_mesh_inquiry_id);

CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_adapter_payloads_seed
    ON proactive_seed_mesh_adapter_payloads (proactive_candidate_seed_id);

CREATE INDEX IF NOT EXISTS idx_proactive_seed_mesh_adapter_payloads_market
    ON proactive_seed_mesh_adapter_payloads (market_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS proactive_seed_mesh_adapter_runs (
    id BIGSERIAL PRIMARY KEY,
    adapter_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    eligible_requests INTEGER NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    partial_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
