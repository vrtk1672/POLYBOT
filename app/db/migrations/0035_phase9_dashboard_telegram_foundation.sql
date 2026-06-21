CREATE TABLE IF NOT EXISTS operator_control_actions (
    id UUID PRIMARY KEY,
    action_class TEXT NOT NULL CHECK (action_class IN ('PAUSE', 'RESUME', 'KILL')),
    requested_via TEXT NOT NULL CHECK (requested_via IN ('TELEGRAM', 'API', 'DASHBOARD')),
    requested_by TEXT NULL,
    command_text TEXT NULL,
    status_class TEXT NOT NULL CHECK (status_class IN ('PLACEHOLDER', 'REJECTED')),
    reason_text TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_operator_control_actions_created_at
    ON operator_control_actions (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_operator_control_actions_action
    ON operator_control_actions (action_class, created_at DESC);

CREATE TABLE IF NOT EXISTS alert_events (
    id UUID PRIMARY KEY,
    event_class TEXT NOT NULL CHECK (
        event_class IN (
            'CANDIDATE_SELECTED',
            'INVALIDATION_WARNING',
            'FEED_FAILURE',
            'SERVICE_CRASH',
            'RISK_OVERLOAD',
            'CRITICAL_HEALTH_DEGRADATION'
        )
    ),
    severity_class TEXT NOT NULL CHECK (severity_class IN ('INFO', 'WARNING', 'CRITICAL')),
    title TEXT NOT NULL,
    body_text TEXT NOT NULL,
    dedupe_key TEXT NULL,
    source_ref TEXT NULL,
    delivery_status_class TEXT NOT NULL CHECK (delivery_status_class IN ('PENDING', 'DELIVERED', 'SKIPPED', 'FAILED')),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_events_created_at
    ON alert_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alert_events_event_class
    ON alert_events (event_class, severity_class, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alert_events_dedupe_key
    ON alert_events (dedupe_key, created_at DESC);
