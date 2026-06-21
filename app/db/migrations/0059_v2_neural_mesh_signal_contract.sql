CREATE TABLE IF NOT EXISTS neuron_signals (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL UNIQUE,
    neuron TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_name TEXT NULL,
    market_id TEXT NULL,
    correlation_id TEXT NULL,
    raw_direction TEXT NULL,
    strength NUMERIC(18,8) NULL,
    confidence NUMERIC(18,8) NULL,
    source_reliability NUMERIC(18,8) NULL,
    freshness_seconds INTEGER NULL,
    status TEXT NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_payload_ref TEXT NULL,
    entity_count INTEGER NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    processed_by_brain BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at TIMESTAMPTZ NULL,
    ttl_seconds INTEGER NULL,
    expires_at TIMESTAMPTZ NULL,
    stale_after_seconds INTEGER NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neuron_signals_neuron_not_blank CHECK (length(trim(neuron)) > 0),
    CONSTRAINT neuron_signals_event_type_not_blank CHECK (length(trim(event_type)) > 0),
    CONSTRAINT neuron_signals_status_check CHECK (status IN ('ACTIVE', 'PARTIAL', 'DEGRADED', 'STALE', 'DISABLED', 'MISSING', 'ERROR')),
    CONSTRAINT neuron_signals_raw_direction_check CHECK (
        raw_direction IS NULL OR raw_direction IN (
            'positive', 'negative', 'neutral', 'mixed', 'unknown',
            'yes_up', 'yes_down', 'no_up', 'no_down',
            'entity_positive', 'entity_negative'
        )
    ),
    CONSTRAINT neuron_signals_strength_range CHECK (strength IS NULL OR (strength >= 0 AND strength <= 1)),
    CONSTRAINT neuron_signals_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT neuron_signals_source_reliability_range CHECK (source_reliability IS NULL OR (source_reliability >= 0 AND source_reliability <= 1)),
    CONSTRAINT neuron_signals_no_trade_action_payload CHECK (
        NOT (
            evidence_json ? 'buy'
            OR evidence_json ? 'sell'
            OR evidence_json ? 'enter_trade'
            OR evidence_json ? 'exit_trade'
            OR evidence_json ? 'trade_decision'
            OR evidence_json ? 'approved'
            OR evidence_json ? 'rejected'
            OR evidence_json ? 'order_id'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_neuron_signals_created_at
    ON neuron_signals (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_neuron_signals_neuron
    ON neuron_signals (neuron, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_neuron_signals_market_id
    ON neuron_signals (market_id, created_at DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_neuron_signals_status
    ON neuron_signals (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_neuron_signals_correlation_id
    ON neuron_signals (correlation_id)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_neuron_signals_processed
    ON neuron_signals (processed_by_brain, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_neuron_signals_source_name
    ON neuron_signals (source_name, created_at DESC)
    WHERE source_name IS NOT NULL;

CREATE TABLE IF NOT EXISTS neuron_signal_entities (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_id TEXT NULL,
    confidence NUMERIC(18,8) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neuron_signal_entities_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_neuron_signal_entities_signal_id
    ON neuron_signal_entities (signal_id);

CREATE INDEX IF NOT EXISTS idx_neuron_signal_entities_entity_name
    ON neuron_signal_entities (entity_name);

CREATE TABLE IF NOT EXISTS neuron_signal_evidence (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL,
    evidence_text TEXT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_url TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_neuron_signal_evidence_signal_id
    ON neuron_signal_evidence (signal_id);

CREATE INDEX IF NOT EXISTS idx_neuron_signal_evidence_type
    ON neuron_signal_evidence (evidence_type);
