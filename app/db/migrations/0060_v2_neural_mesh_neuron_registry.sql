CREATE TABLE IF NOT EXISTS neuron_registry (
    id BIGSERIAL PRIMARY KEY,
    neuron_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    expected_signal_types JSONB NOT NULL DEFAULT '[]'::jsonb,
    producer_source TEXT,
    is_required_for_paper BOOLEAN NOT NULL DEFAULT FALSE,
    is_required_for_live BOOLEAN NOT NULL DEFAULT FALSE,
    default_status TEXT NOT NULL DEFAULT 'MISSING',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    owner_component TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neuron_registry_status_check CHECK (
        default_status IN ('ACTIVE', 'PARTIAL', 'DISABLED', 'MISSING', 'DEGRADED', 'STALE', 'ERROR')
    ),
    CONSTRAINT neuron_registry_name_check CHECK (length(trim(neuron_name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_neuron_registry_category ON neuron_registry (category);
CREATE INDEX IF NOT EXISTS idx_neuron_registry_enabled ON neuron_registry (enabled);

CREATE TABLE IF NOT EXISTS neuron_health (
    id BIGSERIAL PRIMARY KEY,
    neuron_name TEXT NOT NULL UNIQUE REFERENCES neuron_registry(neuron_name) ON DELETE CASCADE,
    runtime_status TEXT NOT NULL DEFAULT 'MISSING',
    health_status TEXT NOT NULL DEFAULT 'MISSING',
    last_signal_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_error_at TIMESTAMPTZ,
    last_error TEXT,
    stale_after_seconds INTEGER NOT NULL DEFAULT 3600 CHECK (stale_after_seconds >= 0),
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    expected_to_emit BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    source_status_name TEXT,
    signal_count_1h INTEGER NOT NULL DEFAULT 0 CHECK (signal_count_1h >= 0),
    signal_count_24h INTEGER NOT NULL DEFAULT 0 CHECK (signal_count_24h >= 0),
    error_count_24h INTEGER NOT NULL DEFAULT 0 CHECK (error_count_24h >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT neuron_health_runtime_status_check CHECK (
        runtime_status IN ('ACTIVE', 'PARTIAL', 'DISABLED', 'MISSING', 'DEGRADED', 'STALE', 'ERROR')
    ),
    CONSTRAINT neuron_health_status_check CHECK (
        health_status IN ('ACTIVE', 'PARTIAL', 'DISABLED', 'MISSING', 'DEGRADED', 'STALE', 'ERROR')
    )
);

CREATE INDEX IF NOT EXISTS idx_neuron_health_runtime_status ON neuron_health (runtime_status);
CREATE INDEX IF NOT EXISTS idx_neuron_health_health_status ON neuron_health (health_status);
CREATE INDEX IF NOT EXISTS idx_neuron_health_is_stale ON neuron_health (is_stale);
CREATE INDEX IF NOT EXISTS idx_neuron_health_updated_at ON neuron_health (updated_at DESC);

INSERT INTO neuron_registry (
    neuron_name,
    display_name,
    category,
    description,
    expected_signal_types,
    producer_source,
    is_required_for_paper,
    is_required_for_live,
    default_status,
    enabled,
    owner_component
)
VALUES
    ('market', 'Market Neuron', 'market', 'Market discovery and price/source availability observations.', '["source_status_observed"]'::jsonb, 'source_status', TRUE, TRUE, 'PARTIAL', TRUE, 'source_status'),
    ('orderbook', 'Orderbook Neuron', 'market', 'Orderbook, spread, and depth source observations.', '["source_status_observed"]'::jsonb, 'source_status', TRUE, TRUE, 'PARTIAL', TRUE, 'source_status'),
    ('liquidity', 'Liquidity Neuron', 'market', 'Liquidity observations and future liquidity signals.', '[]'::jsonb, 'future_connector', TRUE, TRUE, 'MISSING', TRUE, 'market_neuron'),
    ('rules', 'Rules Neuron', 'intelligence', 'Rules, wording, and compliance observations.', '["rules_resolution_status_observed"]'::jsonb, 'rules_resolution', TRUE, TRUE, 'PARTIAL', TRUE, 'rules_resolution_truth'),
    ('resolution', 'Resolution Neuron', 'intelligence', 'Resolution source clarity observations.', '["rules_resolution_status_observed"]'::jsonb, 'rules_resolution', TRUE, TRUE, 'PARTIAL', TRUE, 'rules_resolution_truth'),
    ('news', 'News Neuron', 'intelligence', 'External news catalyst observations.', '["source_status_observed"]'::jsonb, 'source_status', FALSE, TRUE, 'DISABLED', FALSE, 'news_provider'),
    ('social', 'Social / Hype Neuron', 'intelligence', 'Social attention and hype observations.', '["source_status_observed"]'::jsonb, 'source_status', FALSE, TRUE, 'DISABLED', FALSE, 'reddit_or_social_provider'),
    ('whale', 'Whale Neuron', 'intelligence', 'Whale and activity observations.', '["source_status_observed"]'::jsonb, 'source_status', FALSE, TRUE, 'PARTIAL', TRUE, 'polymarket_activity_readonly'),
    ('time', 'Time Neuron', 'market', 'Time-to-close and timing context observations.', '[]'::jsonb, 'future_connector', TRUE, TRUE, 'MISSING', TRUE, 'market_neuron'),
    ('fees', 'Fees Neuron', 'market', 'Fees, rewards, and transaction-cost observations.', '[]'::jsonb, 'future_connector', TRUE, TRUE, 'MISSING', TRUE, 'market_neuron'),
    ('ai', 'AI Neuron', 'ai', 'Local/cloud AI availability and interpretation observations.', '["source_status_observed"]'::jsonb, 'source_status', FALSE, TRUE, 'PARTIAL', TRUE, 'ollama_local_model'),
    ('risk', 'Risk Neuron', 'risk', 'Risk gate and governor observations.', '[]'::jsonb, 'manual', TRUE, TRUE, 'PARTIAL', TRUE, 'risk_gate_governor'),
    ('capital', 'Capital Neuron', 'capital', 'Capital availability and allocation observations.', '[]'::jsonb, 'manual', TRUE, TRUE, 'PARTIAL', TRUE, 'capital_allocator'),
    ('position', 'Position Neuron', 'execution', 'Position state observations.', '[]'::jsonb, 'manual', TRUE, TRUE, 'MISSING', TRUE, 'execution_cortex_v2'),
    ('exit', 'Exit Neuron', 'exit', 'Exit-plan and exit-state observations.', '[]'::jsonb, 'manual', TRUE, TRUE, 'PARTIAL', TRUE, 'exit_cortex_v2'),
    ('source', 'Source Status Neuron', 'system', 'Source availability rollup observations.', '["source_status_observed"]'::jsonb, 'source_status', FALSE, TRUE, 'PARTIAL', TRUE, 'source_status'),
    ('execution', 'Execution Neuron', 'execution', 'Execution-cortex observational status.', '[]'::jsonb, 'manual', TRUE, TRUE, 'PARTIAL', TRUE, 'execution_cortex_v2'),
    ('no_trade', 'No-Trade Neuron', 'system', 'No-trade intelligence observational status.', '[]'::jsonb, 'manual', TRUE, TRUE, 'PARTIAL', TRUE, 'no_trade_intelligence'),
    ('opportunity', 'Opportunity Neuron', 'system', 'Opportunity cortex observational status.', '[]'::jsonb, 'manual', TRUE, TRUE, 'PARTIAL', TRUE, 'opportunity_cortex'),
    ('strategy', 'Strategy Neuron', 'system', 'Strategy-router observational status.', '[]'::jsonb, 'manual', TRUE, TRUE, 'PARTIAL', TRUE, 'strategy_router'),
    ('memory', 'Memory Neuron', 'memory', 'Market-memory observational status.', '[]'::jsonb, 'manual', FALSE, TRUE, 'PARTIAL', TRUE, 'market_memory'),
    ('learning', 'Learning Neuron', 'memory', 'Feedback and learning loop observational status.', '[]'::jsonb, 'manual', FALSE, TRUE, 'PARTIAL', TRUE, 'feedback_learning_loop')
ON CONFLICT (neuron_name) DO NOTHING;
