ALTER TABLE paper_positions
    ADD COLUMN IF NOT EXISTS consistency_status TEXT NOT NULL DEFAULT 'OK',
    ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS invalidation_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS quarantine_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS quarantine_source TEXT NULL,
    ADD COLUMN IF NOT EXISTS quarantine_run_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS excluded_from_active_paper_truth BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_paper_positions_active_truth
    ON paper_positions (current_status, closed_at, excluded_from_active_paper_truth);

CREATE INDEX IF NOT EXISTS idx_paper_positions_quarantine_run
    ON paper_positions (quarantine_run_id)
    WHERE quarantine_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS paper_lineage_quarantine (
    id BIGSERIAL PRIMARY KEY,
    quarantine_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    related_order_id TEXT NULL,
    related_fill_id TEXT NULL,
    related_intent_id TEXT NULL,
    reason TEXT NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor TEXT NOT NULL DEFAULT 'runtime',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT paper_lineage_quarantine_unique_entity UNIQUE (entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_lineage_quarantine_run
    ON paper_lineage_quarantine (run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_paper_lineage_quarantine_entity
    ON paper_lineage_quarantine (entity_type, entity_id);
