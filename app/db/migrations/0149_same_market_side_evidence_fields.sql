ALTER TABLE same_market_side_arbitrations
    ADD COLUMN IF NOT EXISTS yes_side_evidence_score NUMERIC(18,8);

ALTER TABLE same_market_side_arbitrations
    ADD COLUMN IF NOT EXISTS no_side_evidence_score NUMERIC(18,8);

ALTER TABLE same_market_side_arbitrations
    ADD COLUMN IF NOT EXISTS yes_evidence_quality TEXT;

ALTER TABLE same_market_side_arbitrations
    ADD COLUMN IF NOT EXISTS no_evidence_quality TEXT;

ALTER TABLE same_market_side_arbitrations
    ADD COLUMN IF NOT EXISTS side_unknown_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE same_market_side_arbitrations
    ADD COLUMN IF NOT EXISTS missing_side_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb;
