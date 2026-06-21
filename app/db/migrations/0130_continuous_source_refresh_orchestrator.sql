-- Continuous source refresh truth for Full Mesh runtime.
-- DATA_ONLY audit/status tables only. No execution, order, fill, position, or capital tables.

CREATE TABLE IF NOT EXISTS source_refresh_cycles (
    id bigserial PRIMARY KEY,
    cycle_id text NOT NULL UNIQUE,
    orchestrator_state text NOT NULL,
    sources_checked integer NOT NULL DEFAULT 0,
    sources_refreshed integer NOT NULL DEFAULT 0,
    sources_failed integer NOT NULL DEFAULT 0,
    sources_no_new_data integer NOT NULL DEFAULT 0,
    derived_signals_created integer NOT NULL DEFAULT 0,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_source_refresh_cycles_completed_desc
    ON source_refresh_cycles (completed_at DESC NULLS LAST, id DESC);

CREATE TABLE IF NOT EXISTS source_refresh_status (
    id bigserial PRIMARY KEY,
    source_name text NOT NULL UNIQUE,
    source_type text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    refresh_mode text NOT NULL,
    candidate_scoped_supported boolean NOT NULL DEFAULT false,
    market_level_supported boolean NOT NULL DEFAULT true,
    directional_supported boolean NOT NULL DEFAULT false,
    last_refresh_attempt_at timestamptz NULL,
    last_successful_refresh_at timestamptz NULL,
    latest_data_at timestamptz NULL,
    latest_error_at timestamptz NULL,
    latest_error_code text NULL,
    refresh_interval_seconds integer NOT NULL DEFAULT 0,
    ttl_seconds integer NOT NULL DEFAULT 0,
    freshness_seconds integer NULL,
    refresh_state text NOT NULL DEFAULT 'UNKNOWN',
    rows_total integer NOT NULL DEFAULT 0,
    rows_last_24h integer NOT NULL DEFAULT 0,
    rows_last_1h integer NOT NULL DEFAULT 0,
    rows_last_15m integer NOT NULL DEFAULT 0,
    candidate_linked_rows integer NOT NULL DEFAULT 0,
    directional_rows integer NOT NULL DEFAULT 0,
    safe_to_refresh_data_only boolean NOT NULL DEFAULT true,
    required_config_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
    missing_config_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
    blocker_code text NULL,
    required_to_pass jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT source_refresh_status_data_only_safety_check
        CHECK (safe_to_refresh_data_only = true)
);

CREATE INDEX IF NOT EXISTS idx_source_refresh_status_state
    ON source_refresh_status (refresh_state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_refresh_status_type
    ON source_refresh_status (source_type, source_name);
