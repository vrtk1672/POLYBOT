CREATE TABLE IF NOT EXISTS ai_context_router_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    source_component TEXT NOT NULL,
    session_id TEXT NULL,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    provider_order_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_provider TEXT NULL,
    status TEXT NOT NULL,
    final_reason TEXT NOT NULL,
    providers_attempted_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    latency_ms INTEGER NOT NULL DEFAULT 0,
    prompt_hash TEXT NOT NULL,
    response_hash TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ai_context_router_runs_status_chk CHECK (status IN ('OK', 'AI_CONTEXT_UNAVAILABLE', 'AI_DEGRADED', 'DISABLED_BY_POLICY', 'SYSTEM_POWER_OFF'))
);

CREATE INDEX IF NOT EXISTS idx_ai_context_router_runs_status
    ON ai_context_router_runs (status, finished_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_context_router_runs_provider
    ON ai_context_router_runs (selected_provider, finished_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_context_router_runs_market
    ON ai_context_router_runs (market_id, finished_at DESC)
    WHERE market_id IS NOT NULL;
