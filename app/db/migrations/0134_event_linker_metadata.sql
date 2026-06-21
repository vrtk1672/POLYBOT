ALTER TABLE event_to_market_recall
    ADD COLUMN IF NOT EXISTS matched_aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS confidence_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS semantic_score NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN',
    ADD COLUMN IF NOT EXISTS candidate_actionability_hint TEXT NOT NULL DEFAULT 'WATCH_ONLY',
    ADD COLUMN IF NOT EXISTS guardrail_reason TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_actionability_hint
    ON event_to_market_recall (candidate_actionability_hint, link_confidence DESC);

CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_token_side_state
    ON event_to_market_recall (token_side_resolution_state, link_confidence DESC);
