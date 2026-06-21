CREATE TABLE IF NOT EXISTS risk_evidence_mesh_evaluations (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL UNIQUE,
    subject_type TEXT NOT NULL CHECK (subject_type IN ('FRESH_SEED','PAPER_CANDIDATE','PAPER_INTENT','PAPER_POSITION','LIFECYCLE_PLAN')),
    subject_id TEXT NOT NULL,
    market_id TEXT NULL,
    condition_id TEXT NULL,
    side TEXT NULL,
    token_id TEXT NULL,
    critical_evidence_present_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    critical_evidence_missing_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    supporting_evidence_present_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_context_missing_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    blocking_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_quality_score NUMERIC(10,6) NOT NULL DEFAULT 0,
    edge_source_type TEXT NOT NULL CHECK (edge_source_type IN (
        'PRICE_PAYOUT_ASYMMETRY',
        'NEWS_REPRICING_SIGNAL',
        'WHALE_SIGNAL',
        'ORDERBOOK_LIQUIDITY_SETUP',
        'NEAR_RESOLUTION_PAYOUT',
        'CAPITAL_EFFICIENCY_SETUP',
        'RULES_CLARITY_EDGE',
        'AI_CONTEXT_EDGE',
        'MULTI_FACTOR_MESH_EDGE',
        'NO_SOURCE_BACKED_EDGE',
        'UNKNOWN'
    )),
    edge_status TEXT NOT NULL CHECK (edge_status IN (
        'SOURCE_BACKED_EDGE_PRESENT',
        'EDGE_WEAK',
        'NO_SOURCE_BACKED_EDGE',
        'EDGE_UNKNOWN',
        'EDGE_NOT_REQUIRED_FOR_WATCH',
        'EDGE_NOT_EVALUATED'
    )),
    risk_decision TEXT NOT NULL CHECK (risk_decision IN ('RISK_SUPPORT','RISK_WATCH','RISK_REVIEW','RISK_BLOCK')),
    risk_blocker_subtype TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_evidence_mesh_sources (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES risk_evidence_mesh_evaluations(evaluation_id) ON DELETE CASCADE,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    contribution_summary TEXT NOT NULL,
    truth_state TEXT NULL,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evaluation_id, source_table, source_record_id, source_type)
);

CREATE INDEX IF NOT EXISTS idx_risk_evidence_mesh_subject_created
    ON risk_evidence_mesh_evaluations (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_risk_evidence_mesh_market_created
    ON risk_evidence_mesh_evaluations (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_risk_evidence_mesh_decision_created
    ON risk_evidence_mesh_evaluations (risk_decision, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_risk_evidence_mesh_blocker_created
    ON risk_evidence_mesh_evaluations (risk_blocker_subtype, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_risk_evidence_mesh_edge_created
    ON risk_evidence_mesh_evaluations (edge_source_type, created_at DESC);
