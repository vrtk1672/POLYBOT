-- V2 Neural Mesh Part 3B: Position Thesis Profile Contract.
-- This extends the Part 3A graph thesis table into a formal, non-executing
-- contract for future Paper/Shadow/Live positions.

ALTER TABLE position_thesis_profiles
    ADD COLUMN IF NOT EXISTS completeness_score NUMERIC(10, 6),
    ADD COLUMN IF NOT EXISTS paper_ready BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS live_ready BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS coordinator_decision_id TEXT,
    ADD COLUMN IF NOT EXISTS brain_output_id TEXT,
    ADD COLUMN IF NOT EXISTS source_signal_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS risk_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS thesis_version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS created_by TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_by TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE position_thesis_profiles
    ALTER COLUMN source_signal_ids_json SET DEFAULT '[]'::jsonb,
    ALTER COLUMN risk_flags_json SET DEFAULT '[]'::jsonb,
    ALTER COLUMN metadata_json SET DEFAULT '{}'::jsonb,
    ALTER COLUMN thesis_version SET DEFAULT 1,
    ALTER COLUMN paper_ready SET DEFAULT false,
    ALTER COLUMN live_ready SET DEFAULT false;

UPDATE position_thesis_profiles
SET
    source_signal_ids_json = COALESCE(source_signal_ids_json, '[]'::jsonb),
    risk_flags_json = COALESCE(risk_flags_json, '[]'::jsonb),
    metadata_json = COALESCE(metadata_json, '{}'::jsonb),
    thesis_version = COALESCE(thesis_version, 1),
    paper_ready = COALESCE(paper_ready, false),
    live_ready = COALESCE(live_ready, false);

ALTER TABLE position_thesis_profiles
    DROP CONSTRAINT IF EXISTS position_thesis_profiles_status_contract_check;

ALTER TABLE position_thesis_profiles
    ADD CONSTRAINT position_thesis_profiles_status_contract_check
    CHECK (status IN ('DRAFT', 'ACTIVE', 'NEEDS_REVIEW', 'INVALIDATED', 'EXPIRED', 'ARCHIVED'));

ALTER TABLE position_thesis_profiles
    DROP CONSTRAINT IF EXISTS position_thesis_profiles_side_contract_check;

ALTER TABLE position_thesis_profiles
    ADD CONSTRAINT position_thesis_profiles_side_contract_check
    CHECK (side IS NULL OR side IN ('YES', 'NO', 'UNKNOWN'));

ALTER TABLE position_thesis_profiles
    DROP CONSTRAINT IF EXISTS position_thesis_profiles_completeness_range_check;

ALTER TABLE position_thesis_profiles
    ADD CONSTRAINT position_thesis_profiles_completeness_range_check
    CHECK (completeness_score IS NULL OR (completeness_score >= 0 AND completeness_score <= 1));

ALTER TABLE position_thesis_profiles
    DROP CONSTRAINT IF EXISTS position_thesis_profiles_live_requires_paper_check;

ALTER TABLE position_thesis_profiles
    ADD CONSTRAINT position_thesis_profiles_live_requires_paper_check
    CHECK (live_ready = false OR paper_ready = true);

ALTER TABLE position_thesis_profiles
    DROP CONSTRAINT IF EXISTS position_thesis_profiles_version_positive_check;

ALTER TABLE position_thesis_profiles
    ADD CONSTRAINT position_thesis_profiles_version_positive_check
    CHECK (thesis_version >= 1);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_paper_ready
    ON position_thesis_profiles (paper_ready);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_live_ready
    ON position_thesis_profiles (live_ready);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_completeness
    ON position_thesis_profiles (completeness_score);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_coordinator_decision_id
    ON position_thesis_profiles (coordinator_decision_id);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_brain_output_id
    ON position_thesis_profiles (brain_output_id);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_reviewed_at
    ON position_thesis_profiles (reviewed_at);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_expires_at
    ON position_thesis_profiles (expires_at);

CREATE TABLE IF NOT EXISTS position_thesis_validation_events (
    id BIGSERIAL PRIMARY KEY,
    thesis_id TEXT NOT NULL REFERENCES position_thesis_profiles(thesis_id) ON DELETE CASCADE,
    validation_status TEXT NOT NULL,
    completeness_score NUMERIC(10, 6) CHECK (completeness_score IS NULL OR (completeness_score >= 0 AND completeness_score <= 1)),
    paper_ready BOOLEAN NOT NULL DEFAULT false,
    live_ready BOOLEAN NOT NULL DEFAULT false,
    missing_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    validation_errors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_position_thesis_validation_events_thesis_id
    ON position_thesis_validation_events (thesis_id);

CREATE INDEX IF NOT EXISTS idx_position_thesis_validation_events_status
    ON position_thesis_validation_events (validation_status);

CREATE INDEX IF NOT EXISTS idx_position_thesis_validation_events_created_at
    ON position_thesis_validation_events (created_at DESC);
