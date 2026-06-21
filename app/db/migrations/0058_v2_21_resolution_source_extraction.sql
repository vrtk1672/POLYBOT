ALTER TABLE market_rules
    ADD COLUMN IF NOT EXISTS resolution_source_status TEXT NOT NULL DEFAULT 'MISSING',
    ADD COLUMN IF NOT EXISTS resolution_source_type TEXT NOT NULL DEFAULT 'MISSING',
    ADD COLUMN IF NOT EXISTS resolution_source_evidence TEXT NULL,
    ADD COLUMN IF NOT EXISTS resolution_source_confidence NUMERIC(18,8) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS resolution_source_penalty NUMERIC(18,8) NOT NULL DEFAULT 0.45,
    ADD COLUMN IF NOT EXISTS resolution_source_hard_block BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_market_rules_resolution_source_status
    ON market_rules (resolution_source_status, resolution_source_type);
