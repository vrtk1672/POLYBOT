CREATE TABLE IF NOT EXISTS position_awareness (
    id BIGSERIAL PRIMARY KEY,
    awareness_id TEXT NOT NULL UNIQUE,
    position_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    market_id TEXT NULL,
    side TEXT NULL,
    entry_price NUMERIC(18, 8) NULL,
    current_price NUMERIC(18, 8) NULL,
    pnl NUMERIC(18, 8) NULL,
    pnl_pct NUMERIC(18, 8) NULL,
    exposure NUMERIC(18, 8) NULL,
    age_minutes INTEGER NULL,
    liquidity_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    risk_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    exit_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    capital_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    coordinator_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    awareness_score NUMERIC NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT position_awareness_score_chk CHECK (awareness_score >= 0 AND awareness_score <= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_position_awareness_position
    ON position_awareness (position_id);

CREATE INDEX IF NOT EXISTS idx_position_awareness_session
    ON position_awareness (session_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_position_awareness_market
    ON position_awareness (market_id, updated_at DESC)
    WHERE market_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS position_reactions (
    id BIGSERIAL PRIMARY KEY,
    reaction_id TEXT NOT NULL UNIQUE,
    position_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    reaction_type TEXT NOT NULL,
    source_event_id TEXT NULL,
    source_domain TEXT NOT NULL,
    source_component TEXT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    summary TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT position_reactions_type_chk CHECK (reaction_type IN (
        'ADVERSE_NEWS',
        'POSITIVE_NEWS',
        'WHALE_ENTRY',
        'WHALE_EXIT',
        'LIQUIDITY_DROP',
        'LIQUIDITY_IMPROVED',
        'SPREAD_WIDENED',
        'SPREAD_IMPROVED',
        'RISK_INCREASED',
        'RISK_DECREASED',
        'EXIT_DEGRADED',
        'EXIT_IMPROVED',
        'PNL_RISING',
        'PNL_FALLING',
        'CAPITAL_PRESSURE',
        'POSITION_AGING',
        'NO_REACTION'
    )),
    CONSTRAINT position_reactions_severity_chk CHECK (severity IN ('INFO', 'WARN', 'CRITICAL'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_position_reactions_source
    ON position_reactions (
        position_id,
        session_id,
        reaction_type,
        COALESCE(source_event_id, ''),
        source_domain,
        COALESCE(source_component, '')
    );

CREATE INDEX IF NOT EXISTS idx_position_reactions_position
    ON position_reactions (position_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_position_reactions_session
    ON position_reactions (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS position_context_sources (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_position_context_source
    ON position_context_sources (position_id, session_id, source_table, source_record_id, source_domain);

CREATE INDEX IF NOT EXISTS idx_position_context_sources_position
    ON position_context_sources (position_id, linked_at DESC);

CREATE INDEX IF NOT EXISTS idx_position_context_sources_session
    ON position_context_sources (session_id, linked_at DESC);
