CREATE TABLE IF NOT EXISTS neuron_intelligence_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    cycle_id TEXT NULL,
    system_power TEXT NOT NULL DEFAULT 'ON',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL,
    candidates_checked INTEGER NOT NULL DEFAULT 0,
    rules_evidence_count INTEGER NOT NULL DEFAULT 0,
    liquidity_evidence_count INTEGER NOT NULL DEFAULT 0,
    fees_evidence_count INTEGER NOT NULL DEFAULT 0,
    time_evidence_count INTEGER NOT NULL DEFAULT 0,
    news_evidence_count INTEGER NOT NULL DEFAULT 0,
    blocked_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neuron_intelligence_runs_status_check CHECK (
        status IN ('OK', 'SYSTEM_POWER_OFF', 'NO_CANDIDATES', 'BLOCKED', 'DEGRADED', 'ERROR')
    )
);

CREATE INDEX IF NOT EXISTS idx_neuron_intelligence_runs_created
    ON neuron_intelligence_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS neuron_intelligence_evidence (
    id BIGSERIAL PRIMARY KEY,
    evidence_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES neuron_intelligence_runs(run_id) ON DELETE CASCADE,
    cycle_id TEXT NULL,
    candidate_id TEXT NULL,
    market_id TEXT NOT NULL,
    side TEXT NULL,
    neuron_name TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_record_id TEXT NULL,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    score NUMERIC(18, 8) NULL,
    confidence NUMERIC(18, 8) NULL,
    scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    consumed_by_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    blockers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    human_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_neuron_intelligence_evidence_market
    ON neuron_intelligence_evidence (market_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_neuron_intelligence_evidence_neuron
    ON neuron_intelligence_evidence (neuron_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_neuron_intelligence_evidence_candidate
    ON neuron_intelligence_evidence (candidate_id)
    WHERE candidate_id IS NOT NULL;
