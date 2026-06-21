-- V2.5 Rules / Wording / Compliance Neuron

ALTER TABLE market_rules ADD COLUMN IF NOT EXISTS resolution_source_url TEXT NULL;
ALTER TABLE market_rules ADD COLUMN IF NOT EXISTS settlement_method TEXT NULL;
ALTER TABLE market_rules ADD COLUMN IF NOT EXISTS deadline_at TIMESTAMPTZ NULL;
ALTER TABLE market_rules ADD COLUMN IF NOT EXISTS rules_hash TEXT NULL;
ALTER TABLE market_rules ADD COLUMN IF NOT EXISTS ambiguity_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS rules_analysis (
    id BIGSERIAL PRIMARY KEY,
    rules_analysis_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    rules_hash TEXT NULL,
    analysis_version TEXT NOT NULL DEFAULT 'v2.5',
    rules_text_present BOOLEAN NOT NULL DEFAULT false,
    resolution_source_present BOOLEAN NOT NULL DEFAULT false,
    deadline_present BOOLEAN NOT NULL DEFAULT false,
    settlement_method TEXT NULL,
    deadline_at TIMESTAMPTZ NULL,
    ambiguous_terms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    edge_cases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    dangerous_edge_cases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    wording_risk NUMERIC NOT NULL DEFAULT 0,
    dispute_risk NUMERIC NOT NULL DEFAULT 0,
    resolution_clarity NUMERIC NOT NULL DEFAULT 0,
    source_verification_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    jurisdiction_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    compliance_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    recommendation TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
    cannot_trade_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT rules_analysis_recommendation_chk CHECK (recommendation IN ('TRADE_ALLOWED','NO_TRADE','REVIEW_REQUIRED','PENALIZE_HEAVILY')),
    CONSTRAINT rules_analysis_source_status_chk CHECK (source_verification_status IN ('UNKNOWN','VERIFIED','UNVERIFIED','BLOCKED','WARNING','CLEAR','BROKEN','MANUAL_REVIEW')),
    CONSTRAINT rules_analysis_jurisdiction_status_chk CHECK (jurisdiction_status IN ('UNKNOWN','VERIFIED','UNVERIFIED','BLOCKED','WARNING','CLEAR')),
    CONSTRAINT rules_analysis_compliance_status_chk CHECK (compliance_status IN ('UNKNOWN','VERIFIED','UNVERIFIED','BLOCKED','WARNING','CLEAR'))
);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_market_id ON rules_analysis (market_id);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_rules_hash ON rules_analysis (rules_hash);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_wording_risk ON rules_analysis (wording_risk);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_dispute_risk ON rules_analysis (dispute_risk);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_resolution_clarity ON rules_analysis (resolution_clarity);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_compliance_status ON rules_analysis (compliance_status);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_recommendation ON rules_analysis (recommendation);
CREATE INDEX IF NOT EXISTS idx_rules_analysis_created_at ON rules_analysis (created_at);

CREATE TABLE IF NOT EXISTS wording_risk_scores (
    id BIGSERIAL PRIMARY KEY,
    wording_risk_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    rules_analysis_id TEXT NULL,
    rules_hash TEXT NULL,
    ambiguity_score NUMERIC NOT NULL DEFAULT 0,
    deadline_risk NUMERIC NOT NULL DEFAULT 0,
    source_risk NUMERIC NOT NULL DEFAULT 0,
    scope_risk NUMERIC NOT NULL DEFAULT 0,
    settlement_risk NUMERIC NOT NULL DEFAULT 0,
    edge_case_risk NUMERIC NOT NULL DEFAULT 0,
    contradiction_risk NUMERIC NOT NULL DEFAULT 0,
    total_wording_risk NUMERIC NOT NULL DEFAULT 0,
    risk_terms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_wording_risk_market_id ON wording_risk_scores (market_id);
CREATE INDEX IF NOT EXISTS idx_wording_risk_analysis_id ON wording_risk_scores (rules_analysis_id);
CREATE INDEX IF NOT EXISTS idx_wording_risk_total ON wording_risk_scores (total_wording_risk);
CREATE INDEX IF NOT EXISTS idx_wording_risk_created_at ON wording_risk_scores (created_at);

CREATE TABLE IF NOT EXISTS compliance_blocks (
    id BIGSERIAL PRIMARY KEY,
    compliance_block_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    block_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    reason TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'rules_neuron',
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT compliance_block_type_chk CHECK (block_type IN ('MISSING_RULES','UNCLEAR_RESOLUTION','UNVERIFIED_SOURCE','JURISDICTION_BLOCK','AMBIGUOUS_DEADLINE','DISPUTE_RISK_HIGH','PROHIBITED_CATEGORY','MANUAL_BLOCK')),
    CONSTRAINT compliance_block_severity_chk CHECK (severity IN ('INFO','WARNING','BLOCKING'))
);
CREATE INDEX IF NOT EXISTS idx_compliance_blocks_market_id ON compliance_blocks (market_id);
CREATE INDEX IF NOT EXISTS idx_compliance_blocks_type ON compliance_blocks (block_type);
CREATE INDEX IF NOT EXISTS idx_compliance_blocks_severity ON compliance_blocks (severity);
CREATE INDEX IF NOT EXISTS idx_compliance_blocks_active ON compliance_blocks (active);
CREATE INDEX IF NOT EXISTS idx_compliance_blocks_created_at ON compliance_blocks (created_at);

CREATE TABLE IF NOT EXISTS resolution_sources (
    id BIGSERIAL PRIMARY KEY,
    resolution_source_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    source_name TEXT NULL,
    source_url TEXT NULL,
    source_domain TEXT NULL,
    verification_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    verification_reason TEXT NULL,
    last_checked_at TIMESTAMPTZ NULL,
    reliability_score NUMERIC NOT NULL DEFAULT 0.50,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT resolution_source_status_chk CHECK (verification_status IN ('UNKNOWN','VERIFIED','UNVERIFIED','BROKEN','MANUAL_REVIEW','WARNING'))
);
CREATE INDEX IF NOT EXISTS idx_resolution_sources_market_id ON resolution_sources (market_id);
CREATE INDEX IF NOT EXISTS idx_resolution_sources_domain ON resolution_sources (source_domain);
CREATE INDEX IF NOT EXISTS idx_resolution_sources_status ON resolution_sources (verification_status);
CREATE INDEX IF NOT EXISTS idx_resolution_sources_reliability ON resolution_sources (reliability_score);

CREATE TABLE IF NOT EXISTS rules_ai_analysis (
    id BIGSERIAL PRIMARY KEY,
    rules_ai_analysis_id TEXT NOT NULL UNIQUE,
    market_id TEXT NOT NULL,
    rules_analysis_id TEXT NULL,
    ai_request_id TEXT NULL,
    task_type TEXT NOT NULL,
    analysis_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence NUMERIC NULL,
    risk_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_rules_ai_market_id ON rules_ai_analysis (market_id);
CREATE INDEX IF NOT EXISTS idx_rules_ai_analysis_id ON rules_ai_analysis (rules_analysis_id);
CREATE INDEX IF NOT EXISTS idx_rules_ai_ai_request_id ON rules_ai_analysis (ai_request_id);
CREATE INDEX IF NOT EXISTS idx_rules_ai_task_type ON rules_ai_analysis (task_type);
CREATE INDEX IF NOT EXISTS idx_rules_ai_confidence ON rules_ai_analysis (confidence);
