CREATE TABLE IF NOT EXISTS multi_trigger_candidate_triggers (
    id BIGSERIAL PRIMARY KEY,
    multi_trigger_id TEXT NOT NULL UNIQUE,
    trigger_run_id TEXT,
    trigger_type TEXT NOT NULL,
    market_memory_id TEXT,
    market_id TEXT,
    condition_id TEXT,
    source_event_id TEXT,
    targeted_revalidation_id TEXT,
    orderbook_snapshot_id TEXT,
    payout_odds_evaluation_id TEXT,
    market_movement_id TEXT,
    orderbook_signal_id TEXT,
    technical_signal_id TEXT,
    whale_event_id TEXT,
    signal_quality_id TEXT,
    signal_processing_id TEXT,
    side_hint TEXT NOT NULL DEFAULT 'SIDE_UNKNOWN',
    side_confidence NUMERIC NOT NULL DEFAULT 0,
    trigger_strength NUMERIC NOT NULL DEFAULT 0,
    trigger_confidence NUMERIC NOT NULL DEFAULT 0,
    trigger_score NUMERIC NOT NULL DEFAULT 0,
    freshness_seconds INTEGER,
    evidence_summary TEXT,
    trigger_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    guardrail_blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    watch_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    research_priority_band TEXT,
    research_priority_score NUMERIC NOT NULL DEFAULT 0,
    seed_generation_state TEXT NOT NULL DEFAULT 'SKIPPED',
    proactive_candidate_seed_id TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_multi_trigger_candidate_triggers_market
    ON multi_trigger_candidate_triggers (market_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_multi_trigger_candidate_triggers_type
    ON multi_trigger_candidate_triggers (trigger_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_multi_trigger_candidate_triggers_state
    ON multi_trigger_candidate_triggers (seed_generation_state, updated_at DESC);

CREATE TABLE IF NOT EXISTS multi_trigger_candidate_generation_runs (
    id BIGSERIAL PRIMARY KEY,
    trigger_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    triggers_detected INTEGER NOT NULL DEFAULT 0,
    eligible_triggers INTEGER NOT NULL DEFAULT 0,
    watch_only_triggers INTEGER NOT NULL DEFAULT 0,
    blocked_triggers INTEGER NOT NULL DEFAULT 0,
    duplicate_triggers INTEGER NOT NULL DEFAULT 0,
    seeds_generated INTEGER NOT NULL DEFAULT 0,
    yes_seeds INTEGER NOT NULL DEFAULT 0,
    no_seeds INTEGER NOT NULL DEFAULT 0,
    side_unknown_seeds INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE proactive_candidate_seeds
    ADD COLUMN IF NOT EXISTS multi_trigger_id TEXT,
    ADD COLUMN IF NOT EXISTS trigger_type TEXT,
    ADD COLUMN IF NOT EXISTS trigger_score NUMERIC,
    ADD COLUMN IF NOT EXISTS trigger_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS seed_generation_source TEXT NOT NULL DEFAULT 'EVENT_DRIVEN';

CREATE INDEX IF NOT EXISTS idx_proactive_candidate_seeds_multi_trigger
    ON proactive_candidate_seeds (multi_trigger_id)
    WHERE multi_trigger_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_proactive_candidate_seeds_trigger_type
    ON proactive_candidate_seeds (trigger_type, updated_at DESC)
    WHERE trigger_type IS NOT NULL;
