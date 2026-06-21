CREATE TABLE IF NOT EXISTS trade_classification_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    classifier_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_classification_runs_started_at
    ON trade_classification_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS trade_classifications (
    id UUID PRIMARY KEY,
    trade_classification_run_id UUID NOT NULL REFERENCES trade_classification_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    cycle_id UUID NULL REFERENCES cycles(id) ON DELETE SET NULL,
    decision_id UUID NULL REFERENCES decision_ledger(id) ON DELETE SET NULL,
    cognition_summary_id UUID NULL REFERENCES cognition_summaries(id) ON DELETE SET NULL,
    whale_market_score_id UUID NULL REFERENCES whale_market_scores(id) ON DELETE SET NULL,
    primary_trade_type TEXT NOT NULL CHECK (
        primary_trade_type IN (
            'FAST_TRADE', 'RISKY_HIGHER_UPSIDE', 'WHALE_FOLLOW',
            'SLOW_CONVICTION', 'NO_TRADE'
        )
    ),
    secondary_trade_types_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    classification_confidence NUMERIC(6, 5) NOT NULL,
    risk_posture_class TEXT NOT NULL CHECK (
        risk_posture_class IN (
            'LOW_RISK', 'BALANCED', 'ELEVATED_RISK', 'HIGH_RISK', 'DO_NOT_DEPLOY'
        )
    ),
    suggested_bucket_class TEXT NULL CHECK (
        suggested_bucket_class IN (
            'FAST_BUCKET', 'RISKY_BUCKET', 'WHALE_BUCKET', 'CONVICTION_BUCKET', 'NO_BUCKET'
        )
    ),
    classification_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    classification_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    classifier_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_classifications_run_id
    ON trade_classifications (trade_classification_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_classifications_market
    ON trade_classifications (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trade_classifications_primary
    ON trade_classifications (primary_trade_type, classification_confidence DESC, created_at DESC);
