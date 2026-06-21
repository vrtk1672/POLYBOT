ALTER TABLE system_state
    ADD COLUMN IF NOT EXISTS system_power TEXT NOT NULL DEFAULT 'ON',
    ADD COLUMN IF NOT EXISTS system_power_actor TEXT NULL,
    ADD COLUMN IF NOT EXISTS system_power_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS system_power_correlation_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS system_power_transition_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE system_state
    DROP CONSTRAINT IF EXISTS system_state_power_check;

ALTER TABLE system_state
    ADD CONSTRAINT system_state_power_check
        CHECK (system_power IN ('ON', 'OFF'));

UPDATE system_state
SET system_power = COALESCE(system_power, 'ON'),
    system_power_actor = COALESCE(system_power_actor, actor),
    system_power_reason = COALESCE(system_power_reason, 'initial_system_power_on'),
    system_power_transition_at = COALESCE(system_power_transition_at, last_transition_at, now())
WHERE system_power_actor IS NULL
   OR system_power_reason IS NULL;

CREATE TABLE IF NOT EXISTS system_power_transitions (
    id BIGSERIAL PRIMARY KEY,
    transition_id TEXT NOT NULL UNIQUE,
    old_power TEXT NULL CHECK (old_power IS NULL OR old_power IN ('ON', 'OFF')),
    new_power TEXT NOT NULL CHECK (new_power IN ('ON', 'OFF')),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    correlation_id TEXT NULL,
    result TEXT NOT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_system_power_transitions_created
    ON system_power_transitions (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_system_state_power
    ON system_state (system_power, updated_at DESC);
