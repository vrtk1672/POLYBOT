CREATE TABLE IF NOT EXISTS source_event_memory (
    id BIGSERIAL PRIMARY KEY,
    source_event_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    raw_source_type TEXT NULL,
    source_id TEXT NULL,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_url TEXT NULL,
    event_timestamp TIMESTAMPTZ NULL,
    headline TEXT NULL,
    summary TEXT NULL,
    raw_text_hash TEXT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    direction TEXT NOT NULL DEFAULT 'UNKNOWN',
    direction_confidence NUMERIC NOT NULL DEFAULT 0,
    event_confidence NUMERIC NOT NULL DEFAULT 0,
    freshness_seconds INTEGER NULL,
    already_priced_in_state TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
    contradicts_previous_state TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
    supports_existing_thesis_state TEXT NOT NULL DEFAULT 'NOT_EVALUATED',
    top_link_confidence NUMERIC NOT NULL DEFAULT 0,
    linked_markets_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT source_event_memory_source_type_check
        CHECK (source_type IN ('NEWS','RSS','CRYPTOPANIC','WHALE','WALLET_FLOW','ORDERBOOK_MOVEMENT','MARKET_MOVEMENT','SIGNAL','PAYOUT_ODDS','AI_SUMMARY','UNKNOWN')),
    CONSTRAINT source_event_memory_direction_check
        CHECK (direction IN ('YES','NO','NEUTRAL','MIXED','UNKNOWN')),
    CONSTRAINT source_event_memory_priced_check
        CHECK (already_priced_in_state IN ('YES','NO','UNKNOWN','NOT_EVALUATED')),
    CONSTRAINT source_event_memory_contradicts_check
        CHECK (contradicts_previous_state IN ('YES','NO','UNKNOWN','NOT_EVALUATED')),
    CONSTRAINT source_event_memory_supports_check
        CHECK (supports_existing_thesis_state IN ('YES','NO','UNKNOWN','NOT_EVALUATED'))
);

CREATE INDEX IF NOT EXISTS idx_source_event_memory_type_time
    ON source_event_memory (source_type, event_timestamp DESC NULLS LAST, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_event_memory_source_record
    ON source_event_memory (source_table, source_record_id);

CREATE INDEX IF NOT EXISTS idx_source_event_memory_direction
    ON source_event_memory (direction, direction_confidence DESC);

CREATE TABLE IF NOT EXISTS event_to_market_recall (
    id BIGSERIAL PRIMARY KEY,
    recall_id TEXT NOT NULL UNIQUE,
    source_event_id TEXT NOT NULL REFERENCES source_event_memory(source_event_id) ON DELETE CASCADE,
    market_memory_id TEXT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    link_type TEXT NOT NULL,
    link_confidence NUMERIC NOT NULL DEFAULT 0,
    matched_entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    matched_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    direction_for_market TEXT NOT NULL DEFAULT 'UNKNOWN',
    direction_confidence NUMERIC NOT NULL DEFAULT 0,
    eligible_for_targeted_revalidation BOOLEAN NOT NULL DEFAULT false,
    reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT event_to_market_recall_link_type_check
        CHECK (link_type IN ('DIRECT_LINK','LIKELY_LINK','WEAK_LINK','CONTEXT_ONLY','NO_LINK')),
    CONSTRAINT event_to_market_recall_direction_check
        CHECK (direction_for_market IN ('YES','NO','NEUTRAL','MIXED','UNKNOWN'))
);

CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_event
    ON event_to_market_recall (source_event_id, link_confidence DESC);

CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_market
    ON event_to_market_recall (market_id, link_confidence DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_event_to_market_recall_type
    ON event_to_market_recall (link_type, link_confidence DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_event_to_market_recall_unique_subject
    ON event_to_market_recall (source_event_id, COALESCE(market_memory_id, ''), COALESCE(market_id, ''), link_type);

CREATE TABLE IF NOT EXISTS source_event_memory_refresh_runs (
    id BIGSERIAL PRIMARY KEY,
    refresh_run_id TEXT NOT NULL UNIQUE,
    refresh_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ NULL,
    source TEXT NOT NULL DEFAULT 'existing_source_tables',
    events_seen INTEGER NOT NULL DEFAULT 0,
    events_new INTEGER NOT NULL DEFAULT 0,
    events_updated INTEGER NOT NULL DEFAULT 0,
    duplicate_events INTEGER NOT NULL DEFAULT 0,
    links_created INTEGER NOT NULL DEFAULT 0,
    links_updated INTEGER NOT NULL DEFAULT 0,
    unlinked_events INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    latest_error TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_source_event_memory_refresh_completed
    ON source_event_memory_refresh_runs (completed_at DESC NULLS LAST, id DESC);
