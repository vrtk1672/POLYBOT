CREATE TABLE IF NOT EXISTS neuron_producers (
    id BIGSERIAL PRIMARY KEY,
    producer_name TEXT NOT NULL UNIQUE,
    producer_component TEXT NOT NULL,
    neuron_name TEXT NOT NULL REFERENCES neuron_registry(neuron_name) ON DELETE CASCADE,
    source_name TEXT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    expected_signal_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neuron_producers_name_check CHECK (length(trim(producer_name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_neuron_producers_neuron_name ON neuron_producers (neuron_name);
CREATE INDEX IF NOT EXISTS idx_neuron_producers_source_name ON neuron_producers (source_name) WHERE source_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_neuron_producers_enabled ON neuron_producers (enabled);

CREATE TABLE IF NOT EXISTS neuron_signal_bindings (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL UNIQUE REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    neuron_name TEXT NOT NULL,
    producer_name TEXT NOT NULL,
    producer_component TEXT NULL,
    producer_version TEXT NULL,
    source_name TEXT NULL,
    source_status_id BIGINT NULL REFERENCES source_status(id) ON DELETE SET NULL,
    event_log_id BIGINT NULL REFERENCES event_log(id) ON DELETE SET NULL,
    source_event_id TEXT NULL,
    market_id TEXT NULL,
    correlation_id TEXT NULL,
    raw_payload_ref TEXT NULL,
    generated_from TEXT NOT NULL DEFAULT 'unknown',
    lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neuron_signal_bindings_neuron_not_blank CHECK (length(trim(neuron_name)) > 0),
    CONSTRAINT neuron_signal_bindings_producer_not_blank CHECK (length(trim(producer_name)) > 0),
    CONSTRAINT neuron_signal_bindings_generated_from_check CHECK (
        generated_from IN ('source_status', 'rules_resolution', 'event_log', 'manual', 'dashboard', 'future_connector', 'unknown')
    )
);

CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_signal_id ON neuron_signal_bindings (signal_id);
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_neuron_name ON neuron_signal_bindings (neuron_name);
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_producer_name ON neuron_signal_bindings (producer_name);
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_source_name ON neuron_signal_bindings (source_name) WHERE source_name IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_event_log_id ON neuron_signal_bindings (event_log_id) WHERE event_log_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_source_status_id ON neuron_signal_bindings (source_status_id) WHERE source_status_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_market_id ON neuron_signal_bindings (market_id) WHERE market_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_correlation_id ON neuron_signal_bindings (correlation_id) WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_neuron_signal_bindings_created_at ON neuron_signal_bindings (created_at DESC);

INSERT INTO neuron_producers (
    producer_name,
    producer_component,
    neuron_name,
    source_name,
    enabled,
    expected_signal_types,
    description
)
VALUES
    ('source_status_adapter', 'app.services.neuron_signals', 'source', 'source_status', TRUE, '["source_status_observed"]'::jsonb, 'Generic source status to neutral Signal adapter.'),
    ('clob_source_status_adapter', 'app.services.neuron_signals', 'orderbook', 'polymarket_clob_orderbook', TRUE, '["source_status_observed"]'::jsonb, 'CLOB/orderbook source status to neutral Signal adapter.'),
    ('rules_resolution_adapter', 'app.services.neuron_signals', 'rules', 'rules_resolution_truth', TRUE, '["rules_resolution_status_observed"]'::jsonb, 'Rules/resolution truth to neutral Signal adapter.'),
    ('future_news_adapter', 'future_connector', 'news', 'news_provider', FALSE, '[]'::jsonb, 'Future news producer placeholder; disabled.'),
    ('future_social_adapter', 'future_connector', 'social', 'reddit_or_social_provider', FALSE, '[]'::jsonb, 'Future social producer placeholder; disabled.'),
    ('future_whale_adapter', 'future_connector', 'whale', 'polymarket_activity_readonly', FALSE, '[]'::jsonb, 'Future whale producer placeholder; disabled.')
ON CONFLICT (producer_name) DO NOTHING;
