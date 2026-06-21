CREATE TABLE IF NOT EXISTS system_state (
    id BIGSERIAL PRIMARY KEY,
    current_mode TEXT NOT NULL CHECK (current_mode IN ('DATA_ONLY', 'PAPER', 'SHADOW_LIVE', 'SMALL_LIVE', 'ATTACK_MODE', 'COOLDOWN', 'KILL')),
    previous_mode TEXT NULL CHECK (previous_mode IS NULL OR previous_mode IN ('DATA_ONLY', 'PAPER', 'SHADOW_LIVE', 'SMALL_LIVE', 'ATTACK_MODE', 'COOLDOWN', 'KILL')),
    state_status TEXT NOT NULL DEFAULT 'ACTIVE',
    kill_switch_active BOOLEAN NOT NULL DEFAULT false,
    cooldown_active BOOLEAN NOT NULL DEFAULT false,
    attack_mode_active BOOLEAN NOT NULL DEFAULT false,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    correlation_id TEXT NULL,
    last_transition_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_system_state_active_updated_at
    ON system_state (state_status, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS system_state_history (
    id BIGSERIAL PRIMARY KEY,
    from_mode TEXT NULL CHECK (from_mode IS NULL OR from_mode IN ('DATA_ONLY', 'PAPER', 'SHADOW_LIVE', 'SMALL_LIVE', 'ATTACK_MODE', 'COOLDOWN', 'KILL')),
    to_mode TEXT NOT NULL CHECK (to_mode IN ('DATA_ONLY', 'PAPER', 'SHADOW_LIVE', 'SMALL_LIVE', 'ATTACK_MODE', 'COOLDOWN', 'KILL')),
    action TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    allowed BOOLEAN NOT NULL,
    blocked_reason TEXT NULL,
    correlation_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_system_state_history_created_at
    ON system_state_history (created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS runtime_cycles_v2 (
    id BIGSERIAL PRIMARY KEY,
    cycle_id TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('DATA_ONLY', 'PAPER', 'SHADOW_LIVE', 'SMALL_LIVE', 'ATTACK_MODE', 'COOLDOWN', 'KILL')),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    duration_ms INTEGER NULL,
    scanner_started BOOLEAN NOT NULL DEFAULT false,
    scanner_finished BOOLEAN NOT NULL DEFAULT false,
    intelligence_started BOOLEAN NOT NULL DEFAULT false,
    intelligence_finished BOOLEAN NOT NULL DEFAULT false,
    paper_started BOOLEAN NOT NULL DEFAULT false,
    paper_finished BOOLEAN NOT NULL DEFAULT false,
    shadow_started BOOLEAN NOT NULL DEFAULT false,
    shadow_finished BOOLEAN NOT NULL DEFAULT false,
    live_started BOOLEAN NOT NULL DEFAULT false,
    live_finished BOOLEAN NOT NULL DEFAULT false,
    blocked_by_mode BOOLEAN NOT NULL DEFAULT false,
    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_runtime_cycles_v2_started_at
    ON runtime_cycles_v2 (started_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS service_health (
    id BIGSERIAL PRIMARY KEY,
    service_name TEXT NOT NULL UNIQUE,
    service_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'HEALTHY', 'DEGRADED', 'STALE', 'ERROR', 'STOPPED', 'BLOCKED_BY_MODE')),
    last_heartbeat_at TIMESTAMPTZ NULL,
    last_success_at TIMESTAMPTZ NULL,
    last_error_at TIMESTAMPTZ NULL,
    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    lag_seconds INTEGER NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_health_status_updated_at
    ON service_health (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS runtime_incidents (
    id BIGSERIAL PRIMARY KEY,
    severity TEXT NOT NULL,
    source_service TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    message TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    correlation_id TEXT NULL,
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_runtime_incidents_status_severity_last_seen
    ON runtime_incidents (status, severity, last_seen_at DESC);
