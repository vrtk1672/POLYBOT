CREATE TABLE IF NOT EXISTS mesh_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    session_type TEXT NOT NULL,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    position_id TEXT NULL,
    correlation_id TEXT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    priority INTEGER NOT NULL DEFAULT 5,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_event_at TIMESTAMPTZ NULL,
    closed_at TIMESTAMPTZ NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    participant_count INTEGER NOT NULL DEFAULT 0,
    has_conflict BOOLEAN NOT NULL DEFAULT false,
    has_decision BOOLEAN NOT NULL DEFAULT false,
    threat_context BOOLEAN NOT NULL DEFAULT false,
    opportunity_context BOOLEAN NOT NULL DEFAULT false,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT mesh_sessions_type_chk CHECK (session_type IN (
        'MARKET_SESSION',
        'CANDIDATE_SESSION',
        'POSITION_SESSION',
        'OPPORTUNITY_SESSION',
        'THREAT_SESSION',
        'GLOBAL_SESSION',
        'UNASSIGNED_SESSION'
    )),
    CONSTRAINT mesh_sessions_status_chk CHECK (status IN ('OPEN', 'ACTIVE', 'STALE', 'CLOSED')),
    CONSTRAINT mesh_sessions_priority_chk CHECK (priority BETWEEN 0 AND 10)
);

CREATE INDEX IF NOT EXISTS idx_mesh_sessions_type_status
    ON mesh_sessions (session_type, status, last_event_at DESC);

CREATE INDEX IF NOT EXISTS idx_mesh_sessions_market
    ON mesh_sessions (market_id, last_event_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mesh_sessions_candidate
    ON mesh_sessions (candidate_id, last_event_at DESC)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mesh_sessions_position
    ON mesh_sessions (position_id, last_event_at DESC)
    WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mesh_sessions_correlation
    ON mesh_sessions (correlation_id, last_event_at DESC)
    WHERE correlation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS mesh_session_events (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_component TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    role TEXT NOT NULL DEFAULT 'OBSERVATION',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT mesh_session_events_role_chk CHECK (role IN ('PRIMARY', 'CONTEXT', 'THREAT', 'OPPORTUNITY', 'GLOBAL', 'OBSERVATION'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_session_events_session_event
    ON mesh_session_events (session_id, event_id);

CREATE INDEX IF NOT EXISTS idx_mesh_session_events_event
    ON mesh_session_events (event_id);

CREATE INDEX IF NOT EXISTS idx_mesh_session_events_linked
    ON mesh_session_events (linked_at DESC);

CREATE TABLE IF NOT EXISTS mesh_session_participants (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    component TEXT NOT NULL,
    component_type TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    message_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_session_participant
    ON mesh_session_participants (session_id, component);

CREATE INDEX IF NOT EXISTS idx_mesh_session_participants_session
    ON mesh_session_participants (session_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS mesh_session_state (
    session_id TEXT PRIMARY KEY REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    latest_market_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_candidate_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_position_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_risk_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_exit_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_capital_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_news_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_liquidity_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_time_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_fees_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_rules_state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
