CREATE TABLE IF NOT EXISTS mesh_brain_opinions (
    id BIGSERIAL PRIMARY KEY,
    opinion_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    brain_name TEXT NOT NULL,
    brain_type TEXT NOT NULL,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    position_id TEXT NULL,
    stance TEXT NOT NULL,
    confidence NUMERIC NOT NULL DEFAULT 0,
    decision_bias TEXT NOT NULL DEFAULT 'OBSERVE',
    reasoning_summary TEXT NOT NULL,
    consumed_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    stale_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    supporting_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    opposing_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    conflicts_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_brain_opinions_brain_type_chk CHECK (brain_type IN (
        'RISK_BRAIN',
        'EXIT_BRAIN',
        'CAPITAL_BRAIN',
        'CONTEXT_BRAIN',
        'POSITION_BRAIN',
        'COORDINATOR_OBSERVER'
    )),
    CONSTRAINT mesh_brain_opinions_stance_chk CHECK (stance IN ('SUPPORT', 'CAUTION', 'BLOCK', 'NO_SIGNAL')),
    CONSTRAINT mesh_brain_opinions_confidence_chk CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_brain_opinion_session_brain
    ON mesh_brain_opinions (session_id, brain_type);

CREATE INDEX IF NOT EXISTS idx_mesh_brain_opinions_session
    ON mesh_brain_opinions (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_mesh_brain_opinions_brain_type
    ON mesh_brain_opinions (brain_type, stance, created_at DESC);

CREATE TABLE IF NOT EXISTS mesh_brain_consumption_sources (
    id BIGSERIAL PRIMARY KEY,
    opinion_id TEXT NOT NULL REFERENCES mesh_brain_opinions(opinion_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    source_domain TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_status TEXT NOT NULL,
    influence TEXT NOT NULL DEFAULT 'SUPPORTING',
    contribution_summary TEXT NOT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_brain_consumption_sources_influence_chk CHECK (influence IN ('SUPPORTING', 'OPPOSING', 'CONTEXT')),
    CONSTRAINT mesh_brain_consumption_sources_status_chk CHECK (source_status IN ('PRESENT', 'PARTIAL', 'STALE', 'MISSING', 'ERROR', 'FRESH'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_brain_consumption_source
    ON mesh_brain_consumption_sources (opinion_id, source_domain, source_table, source_record_id);

CREATE INDEX IF NOT EXISTS idx_mesh_brain_consumption_sources_session
    ON mesh_brain_consumption_sources (session_id, source_domain, linked_at DESC);

CREATE TABLE IF NOT EXISTS mesh_coordinator_input_bundles (
    id BIGSERIAL PRIMARY KEY,
    bundle_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES mesh_sessions(session_id) ON DELETE CASCADE,
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    position_id TEXT NULL,
    source_brain_count INTEGER NOT NULL DEFAULT 0,
    opinion_count INTEGER NOT NULL DEFAULT 0,
    stance_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    conflicts_detected BOOLEAN NOT NULL DEFAULT false,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    coordinator_ready BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mesh_coordinator_bundle_source_count_chk CHECK (source_brain_count >= 0),
    CONSTRAINT mesh_coordinator_bundle_opinion_count_chk CHECK (opinion_count >= 0),
    CONSTRAINT mesh_coordinator_bundle_conflict_count_chk CHECK (conflict_count >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mesh_coordinator_input_bundle_session
    ON mesh_coordinator_input_bundles (session_id);

CREATE INDEX IF NOT EXISTS idx_mesh_coordinator_input_bundles_created
    ON mesh_coordinator_input_bundles (created_at DESC);
