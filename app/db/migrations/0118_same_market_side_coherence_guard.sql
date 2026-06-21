CREATE TABLE IF NOT EXISTS same_market_side_guard_decisions (
    id BIGSERIAL PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    proposed_side TEXT NOT NULL CHECK (proposed_side IN ('YES', 'NO')),
    proposed_candidate_id TEXT NULL,
    proposed_intent_id TEXT NULL,
    existing_exposure_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    existing_open_positions_count INTEGER NOT NULL DEFAULT 0 CHECK (existing_open_positions_count >= 0),
    existing_opposite_positions_count INTEGER NOT NULL DEFAULT 0 CHECK (existing_opposite_positions_count >= 0),
    existing_same_side_positions_count INTEGER NOT NULL DEFAULT 0 CHECK (existing_same_side_positions_count >= 0),
    existing_opposite_intents_count INTEGER NOT NULL DEFAULT 0 CHECK (existing_opposite_intents_count >= 0),
    existing_same_side_intents_count INTEGER NOT NULL DEFAULT 0 CHECK (existing_same_side_intents_count >= 0),
    recent_opposite_closes_count INTEGER NOT NULL DEFAULT 0 CHECK (recent_opposite_closes_count >= 0),
    batch_opposite_candidates_count INTEGER NOT NULL DEFAULT 0 CHECK (batch_opposite_candidates_count >= 0),
    rationale_type TEXT NULL,
    rationale_source TEXT NULL,
    source_backed BOOLEAN NOT NULL DEFAULT false,
    decision TEXT NOT NULL CHECK (decision IN ('ALLOW', 'BLOCK', 'REVIEW')),
    blocker_reason TEXT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT false,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_same_market_side_guard_market_created
    ON same_market_side_guard_decisions (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_same_market_side_guard_decision_created
    ON same_market_side_guard_decisions (decision, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_same_market_side_guard_candidate
    ON same_market_side_guard_decisions (proposed_candidate_id)
    WHERE proposed_candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_same_market_side_guard_intent
    ON same_market_side_guard_decisions (proposed_intent_id)
    WHERE proposed_intent_id IS NOT NULL;
