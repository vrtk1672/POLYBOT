CREATE TABLE IF NOT EXISTS intelligence_source_registry (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    provider_category TEXT NOT NULL,
    requires_api_key BOOLEAN NOT NULL DEFAULT false,
    required_env_vars JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_env_vars JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'CONFIGURED',
    health_status TEXT NOT NULL DEFAULT 'UNTESTED',
    last_checked_at TIMESTAMPTZ NULL,
    setup_url_or_notes TEXT NOT NULL,
    cost_model TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    enabled_by_default BOOLEAN NOT NULL DEFAULT false,
    neural_event_type TEXT NULL,
    awareness_domain TEXT NULL,
    supports_mock BOOLEAN NOT NULL DEFAULT true,
    target_tables_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT intelligence_source_registry_type_chk CHECK (source_type IN (
        'NEWS',
        'WHALE',
        'SOCIAL',
        'AI_CONTEXT',
        'MARKET_MEMORY'
    )),
    CONSTRAINT intelligence_source_registry_status_chk CHECK (status IN (
        'CONFIGURED',
        'READY',
        'READY_NO_KEY',
        'MISSING_CREDENTIALS',
        'DISABLED_BY_DEFAULT',
        'PARTIAL',
        'ERROR'
    )),
    CONSTRAINT intelligence_source_registry_health_chk CHECK (health_status IN (
        'UNTESTED',
        'READY',
        'READY_NO_KEY',
        'BLOCKED_MISSING_CREDENTIALS',
        'DISABLED',
        'ERROR'
    ))
);

CREATE INDEX IF NOT EXISTS idx_intelligence_source_registry_type
    ON intelligence_source_registry (source_type, priority, provider_name);

CREATE INDEX IF NOT EXISTS idx_intelligence_source_registry_status
    ON intelligence_source_registry (status, health_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS intelligence_source_credentials_status (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES intelligence_source_registry(source_id) ON DELETE CASCADE,
    env_var TEXT NOT NULL,
    required BOOLEAN NOT NULL DEFAULT true,
    present BOOLEAN NOT NULL DEFAULT false,
    validity_status TEXT NOT NULL DEFAULT 'UNTESTED',
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT intelligence_source_credentials_validity_chk CHECK (validity_status IN (
        'PRESENT',
        'MISSING',
        'OPTIONAL_MISSING',
        'UNTESTED',
        'INVALID'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_intelligence_source_credentials_status
    ON intelligence_source_credentials_status (source_id, env_var);

CREATE INDEX IF NOT EXISTS idx_intelligence_source_credentials_missing
    ON intelligence_source_credentials_status (required, present, validity_status);

CREATE TABLE IF NOT EXISTS intelligence_provider_health (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES intelligence_source_registry(source_id) ON DELETE CASCADE,
    health_status TEXT NOT NULL,
    credential_status TEXT NOT NULL,
    readiness_status TEXT NOT NULL,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    latency_ms INTEGER NULL,
    message TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT intelligence_provider_health_status_chk CHECK (health_status IN (
        'UNTESTED',
        'READY',
        'READY_NO_KEY',
        'BLOCKED_MISSING_CREDENTIALS',
        'DISABLED',
        'ERROR'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_intelligence_provider_health_source
    ON intelligence_provider_health (source_id);

CREATE TABLE IF NOT EXISTS intelligence_missing_requirements (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES intelligence_source_registry(source_id) ON DELETE CASCADE,
    env_var TEXT NOT NULL,
    requirement_type TEXT NOT NULL DEFAULT 'ENV_VAR',
    severity TEXT NOT NULL DEFAULT 'REQUIRED',
    next_action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ NULL,
    CONSTRAINT intelligence_missing_requirements_severity_chk CHECK (severity IN (
        'REQUIRED',
        'OPTIONAL',
        'RECOMMENDED'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_intelligence_missing_requirements_open
    ON intelligence_missing_requirements (source_id, env_var)
    WHERE resolved_at IS NULL;

CREATE TABLE IF NOT EXISTS intelligence_connector_tests (
    id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES intelligence_source_registry(source_id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT intelligence_connector_tests_status_chk CHECK (status IN (
        'PASSED',
        'FAILED',
        'SKIPPED',
        'UNTESTED'
    ))
);

CREATE INDEX IF NOT EXISTS idx_intelligence_connector_tests_source
    ON intelligence_connector_tests (source_id, checked_at DESC);
