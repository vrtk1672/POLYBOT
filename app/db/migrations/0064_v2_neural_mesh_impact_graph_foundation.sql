CREATE TABLE IF NOT EXISTS event_entities (
    id BIGSERIAL PRIMARY KEY,
    entity_id TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL CHECK (length(trim(entity_type)) > 0),
    entity_name TEXT NOT NULL CHECK (length(trim(entity_name)) > 0),
    normalized_name TEXT NULL,
    source_signal_id TEXT NULL REFERENCES neuron_signals(signal_id) ON DELETE SET NULL,
    source_event_id TEXT NULL,
    source_name TEXT NULL,
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_event_entities_entity_id
    ON event_entities (entity_id);

CREATE INDEX IF NOT EXISTS idx_event_entities_type
    ON event_entities (entity_type);

CREATE INDEX IF NOT EXISTS idx_event_entities_name
    ON event_entities (entity_name);

CREATE INDEX IF NOT EXISTS idx_event_entities_normalized_name
    ON event_entities (normalized_name)
    WHERE normalized_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_event_entities_source_signal
    ON event_entities (source_signal_id)
    WHERE source_signal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_event_entities_source_event
    ON event_entities (source_event_id)
    WHERE source_event_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS entity_market_links (
    id BIGSERIAL PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES event_entities(entity_id) ON DELETE CASCADE,
    market_id TEXT NOT NULL CHECK (length(trim(market_id)) > 0),
    link_type TEXT NOT NULL CHECK (length(trim(link_type)) > 0),
    link_status TEXT NOT NULL CHECK (link_status IN ('suggested', 'confirmed', 'rejected', 'expired', 'unknown')),
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    evidence_signal_id TEXT NULL REFERENCES neuron_signals(signal_id) ON DELETE SET NULL,
    evidence_event_id TEXT NULL,
    evidence_text TEXT NULL,
    created_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entity_market_links_entity
    ON entity_market_links (entity_id);

CREATE INDEX IF NOT EXISTS idx_entity_market_links_market
    ON entity_market_links (market_id);

CREATE INDEX IF NOT EXISTS idx_entity_market_links_status
    ON entity_market_links (link_status);

CREATE INDEX IF NOT EXISTS idx_entity_market_links_type
    ON entity_market_links (link_type);

CREATE TABLE IF NOT EXISTS signal_market_links (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    market_id TEXT NOT NULL CHECK (length(trim(market_id)) > 0),
    link_type TEXT NOT NULL CHECK (length(trim(link_type)) > 0),
    link_status TEXT NOT NULL CHECK (link_status IN ('suggested', 'confirmed', 'rejected', 'expired', 'unknown')),
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    reason TEXT NULL,
    created_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signal_market_links_signal
    ON signal_market_links (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_market_links_market
    ON signal_market_links (market_id);

CREATE INDEX IF NOT EXISTS idx_signal_market_links_status
    ON signal_market_links (link_status);

CREATE INDEX IF NOT EXISTS idx_signal_market_links_created
    ON signal_market_links (created_at DESC);

CREATE TABLE IF NOT EXISTS signal_position_links (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    position_id TEXT NOT NULL CHECK (length(trim(position_id)) > 0),
    market_id TEXT NULL,
    link_type TEXT NOT NULL CHECK (length(trim(link_type)) > 0),
    link_status TEXT NOT NULL CHECK (link_status IN ('suggested', 'confirmed', 'rejected', 'expired', 'unknown')),
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    reason TEXT NULL,
    created_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signal_position_links_signal
    ON signal_position_links (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_position_links_position
    ON signal_position_links (position_id);

CREATE INDEX IF NOT EXISTS idx_signal_position_links_market
    ON signal_position_links (market_id)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_position_links_status
    ON signal_position_links (link_status);

CREATE INDEX IF NOT EXISTS idx_signal_position_links_created
    ON signal_position_links (created_at DESC);

CREATE TABLE IF NOT EXISTS position_thesis_profiles (
    id BIGSERIAL PRIMARY KEY,
    thesis_id TEXT NOT NULL UNIQUE,
    position_id TEXT NOT NULL CHECK (length(trim(position_id)) > 0),
    market_id TEXT NOT NULL CHECK (length(trim(market_id)) > 0),
    side TEXT NULL,
    entry_thesis TEXT NOT NULL CHECK (length(trim(entry_thesis)) > 0),
    profit_drivers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    invalidation_drivers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    watch_entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    danger_signals_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    take_profit_rules_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    partial_exit_rules_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    emergency_exit_rules_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL CHECK (length(trim(status)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_position_thesis_profiles_thesis
    ON position_thesis_profiles (thesis_id);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_position
    ON position_thesis_profiles (position_id);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_market
    ON position_thesis_profiles (market_id);

CREATE INDEX IF NOT EXISTS idx_position_thesis_profiles_status
    ON position_thesis_profiles (status);

CREATE TABLE IF NOT EXISTS impact_links (
    id BIGSERIAL PRIMARY KEY,
    impact_link_id TEXT NOT NULL UNIQUE,
    signal_id TEXT NULL REFERENCES neuron_signals(signal_id) ON DELETE SET NULL,
    event_id TEXT NULL,
    entity_id TEXT NULL REFERENCES event_entities(entity_id) ON DELETE SET NULL,
    market_id TEXT NULL,
    position_id TEXT NULL,
    thesis_id TEXT NULL REFERENCES position_thesis_profiles(thesis_id) ON DELETE SET NULL,
    brain_output_id TEXT NULL REFERENCES brain_outputs(brain_output_id) ON DELETE SET NULL,
    coordinator_decision_id TEXT NULL REFERENCES coordinator_decisions(coordinator_decision_id) ON DELETE SET NULL,
    impact_scope TEXT NOT NULL CHECK (impact_scope IN ('market', 'position', 'thesis', 'source', 'system', 'unknown')),
    impact_direction TEXT NOT NULL CHECK (impact_direction IN ('favorable', 'adverse', 'neutral', 'mixed', 'unknown')),
    impact_status TEXT NOT NULL CHECK (impact_status IN ('suggested', 'confirmed', 'rejected', 'expired', 'needs_review', 'unknown')),
    impact_strength NUMERIC(10, 6) NULL CHECK (impact_strength IS NULL OR (impact_strength >= 0 AND impact_strength <= 1)),
    confidence NUMERIC(10, 6) NULL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    urgency NUMERIC(10, 6) NULL CHECK (urgency IS NULL OR (urgency >= 0 AND urgency <= 1)),
    cortex_action_hint TEXT NOT NULL CHECK (
        cortex_action_hint IN (
            'WATCH',
            'REVIEW',
            'NO_TRADE_REVIEW',
            'EXIT_REVIEW',
            'OPPORTUNITY_REVIEW',
            'RISK_REVIEW',
            'IGNORE',
            'MEMORY_ONLY',
            'UNKNOWN'
        )
    ),
    reasoning_summary TEXT NULL,
    created_by TEXT NULL,
    ttl_seconds INTEGER NULL CHECK (ttl_seconds IS NULL OR ttl_seconds >= 0),
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT impact_links_subject_required CHECK (
        signal_id IS NOT NULL OR event_id IS NOT NULL OR entity_id IS NOT NULL
    ),
    CONSTRAINT impact_links_target_required CHECK (
        market_id IS NOT NULL OR position_id IS NOT NULL OR thesis_id IS NOT NULL OR impact_scope IN ('system', 'source')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_impact_links_impact_link_id
    ON impact_links (impact_link_id);

CREATE INDEX IF NOT EXISTS idx_impact_links_signal
    ON impact_links (signal_id)
    WHERE signal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_event
    ON impact_links (event_id)
    WHERE event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_entity
    ON impact_links (entity_id)
    WHERE entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_market
    ON impact_links (market_id)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_position
    ON impact_links (position_id)
    WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_thesis
    ON impact_links (thesis_id)
    WHERE thesis_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_brain_output
    ON impact_links (brain_output_id)
    WHERE brain_output_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_coordinator
    ON impact_links (coordinator_decision_id)
    WHERE coordinator_decision_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_impact_links_scope
    ON impact_links (impact_scope);

CREATE INDEX IF NOT EXISTS idx_impact_links_direction
    ON impact_links (impact_direction);

CREATE INDEX IF NOT EXISTS idx_impact_links_status
    ON impact_links (impact_status);

CREATE INDEX IF NOT EXISTS idx_impact_links_action_hint
    ON impact_links (cortex_action_hint);

CREATE INDEX IF NOT EXISTS idx_impact_links_created
    ON impact_links (created_at DESC);
