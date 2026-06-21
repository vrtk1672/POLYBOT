CREATE TABLE IF NOT EXISTS mesh_shared_awareness (
    id BIGSERIAL PRIMARY KEY,
    awareness_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    session_type TEXT NOT NULL,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    position_id TEXT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    freshness_status TEXT NOT NULL DEFAULT 'MISSING',
    completeness_score NUMERIC NOT NULL DEFAULT 0,
    confidence_score NUMERIC NOT NULL DEFAULT 0,
    news_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    whale_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    social_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    rules_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    liquidity_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    orderbook_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    fees_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    time_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    exit_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    capital_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    pnl_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    memory_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    position_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    candidate_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    stale_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_shared_awareness_status_chk CHECK (status IN ('ACTIVE', 'PARTIAL', 'EMPTY', 'ERROR')),
    CONSTRAINT mesh_shared_awareness_freshness_chk CHECK (freshness_status IN ('FRESH', 'PARTIAL', 'STALE', 'MISSING', 'ERROR')),
    CONSTRAINT mesh_shared_awareness_completeness_chk CHECK (completeness_score >= 0 AND completeness_score <= 1),
    CONSTRAINT mesh_shared_awareness_confidence_chk CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_shared_awareness_session
    ON mesh_shared_awareness (session_id);

CREATE INDEX IF NOT EXISTS idx_mesh_shared_awareness_session_type
    ON mesh_shared_awareness (session_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_mesh_shared_awareness_market
    ON mesh_shared_awareness (market_id, updated_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mesh_shared_awareness_candidate
    ON mesh_shared_awareness (candidate_id, updated_at DESC)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mesh_shared_awareness_position
    ON mesh_shared_awareness (position_id, updated_at DESC)
    WHERE position_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS mesh_awareness_sources (
    id BIGSERIAL PRIMARY KEY,
    awareness_id TEXT NOT NULL REFERENCES mesh_shared_awareness(awareness_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    source_domain TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_component TEXT NULL,
    source_created_at TIMESTAMPTZ NULL,
    freshness_status TEXT NOT NULL DEFAULT 'MISSING',
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_awareness_sources_domain_chk CHECK (source_domain IN (
        'NEWS',
        'WHALE',
        'SOCIAL',
        'RULES',
        'LIQUIDITY',
        'ORDERBOOK',
        'FEES',
        'TIME',
        'RISK',
        'EXIT',
        'CAPITAL',
        'PNL',
        'MEMORY',
        'POSITION',
        'CANDIDATE'
    )),
    CONSTRAINT mesh_awareness_sources_freshness_chk CHECK (freshness_status IN ('FRESH', 'STALE', 'PARTIAL', 'MISSING', 'ERROR'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_awareness_source_ref
    ON mesh_awareness_sources (awareness_id, source_domain, source_table, source_record_id);

CREATE INDEX IF NOT EXISTS idx_mesh_awareness_sources_session
    ON mesh_awareness_sources (session_id, source_domain, linked_at DESC);

CREATE INDEX IF NOT EXISTS idx_mesh_awareness_sources_domain
    ON mesh_awareness_sources (source_domain, freshness_status, linked_at DESC);
