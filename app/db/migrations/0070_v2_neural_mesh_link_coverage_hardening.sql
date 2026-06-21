CREATE TABLE IF NOT EXISTS signal_link_coverage_analysis (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    is_linked_to_market BOOLEAN NOT NULL DEFAULT FALSE,
    is_linked_to_position BOOLEAN NOT NULL DEFAULT FALSE,
    is_unlinked BOOLEAN NOT NULL DEFAULT TRUE,
    linkability_status TEXT NOT NULL CHECK (
        linkability_status IN ('LINKED', 'LINKABLE', 'NOT_LINKABLE', 'NEEDS_MORE_EVIDENCE', 'STALE', 'DRY_RUN_ONLY', 'ERROR')
    ),
    primary_unlinked_reason TEXT NOT NULL,
    unlinked_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    has_market_id BOOLEAN NOT NULL DEFAULT FALSE,
    has_entity BOOLEAN NOT NULL DEFAULT FALSE,
    has_source BOOLEAN NOT NULL DEFAULT FALSE,
    has_rules_context BOOLEAN NOT NULL DEFAULT FALSE,
    has_producer BOOLEAN NOT NULL DEFAULT FALSE,
    has_matcher_evidence BOOLEAN NOT NULL DEFAULT FALSE,
    has_raw_payload_ref BOOLEAN NOT NULL DEFAULT FALSE,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_runtime_generated BOOLEAN NOT NULL DEFAULT FALSE,
    is_stale BOOLEAN NOT NULL DEFAULT FALSE,
    suggested_market_id TEXT NULL,
    suggested_market_confidence NUMERIC(10, 6) NULL CHECK (
        suggested_market_confidence IS NULL OR (suggested_market_confidence >= 0 AND suggested_market_confidence <= 1)
    ),
    suggested_market_reason TEXT NULL,
    suggested_link_action TEXT NOT NULL CHECK (
        suggested_link_action IN (
            'NONE',
            'REVIEW_ONLY',
            'SAFE_TO_LINK_EXISTING_MARKET_ID',
            'BLOCKED_WEAK_EVIDENCE',
            'BLOCKED_DRY_RUN_ONLY',
            'BLOCKED_STALE',
            'BLOCKED_MISSING_MARKET',
            'BLOCKED_MISSING_ENTITY',
            'BLOCKED_MISSING_SOURCE',
            'BLOCKED_NO_MATCHER'
        )
    ),
    can_auto_link BOOLEAN NOT NULL DEFAULT FALSE,
    can_feed_brain_after_link BOOLEAN NOT NULL DEFAULT FALSE,
    can_feed_paper_after_link BOOLEAN NOT NULL DEFAULT FALSE,
    analysis_status TEXT NOT NULL CHECK (analysis_status IN ('OK', 'PARTIAL', 'ERROR')),
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT signal_link_coverage_analysis_signal_unique UNIQUE (signal_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_link_coverage_status
    ON signal_link_coverage_analysis (linkability_status);

CREATE INDEX IF NOT EXISTS idx_signal_link_coverage_reason
    ON signal_link_coverage_analysis (primary_unlinked_reason);

CREATE INDEX IF NOT EXISTS idx_signal_link_coverage_analysis_status
    ON signal_link_coverage_analysis (analysis_status);

CREATE INDEX IF NOT EXISTS idx_signal_link_coverage_suggested_market
    ON signal_link_coverage_analysis (suggested_market_id)
    WHERE suggested_market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_link_coverage_can_auto
    ON signal_link_coverage_analysis (can_auto_link);

CREATE INDEX IF NOT EXISTS idx_signal_link_coverage_analyzed
    ON signal_link_coverage_analysis (analyzed_at DESC);

CREATE TABLE IF NOT EXISTS signal_suggested_market_links (
    id BIGSERIAL PRIMARY KEY,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    suggested_market_id TEXT NOT NULL CHECK (length(trim(suggested_market_id)) > 0),
    confidence NUMERIC(10, 6) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT NOT NULL,
    suggestion_status TEXT NOT NULL CHECK (
        suggestion_status IN (
            'REVIEW_ONLY',
            'SAFE_CANDIDATE',
            'REJECTED_WEAK_EVIDENCE',
            'REJECTED_DRY_RUN_ONLY',
            'REJECTED_STALE',
            'APPLIED',
            'ERROR'
        )
    ),
    created_by TEXT NULL,
    is_applied BOOLEAN NOT NULL DEFAULT FALSE,
    applied_at TIMESTAMPTZ NULL,
    rejected_at TIMESTAMPTZ NULL,
    rejection_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT signal_suggested_market_links_unique UNIQUE (signal_id, suggested_market_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_suggested_market_links_signal
    ON signal_suggested_market_links (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_suggested_market_links_market
    ON signal_suggested_market_links (suggested_market_id);

CREATE INDEX IF NOT EXISTS idx_signal_suggested_market_links_status
    ON signal_suggested_market_links (suggestion_status);

CREATE INDEX IF NOT EXISTS idx_signal_suggested_market_links_applied
    ON signal_suggested_market_links (is_applied);

CREATE TABLE IF NOT EXISTS signal_link_coverage_runs (
    id BIGSERIAL PRIMARY KEY,
    requested_limit INTEGER NOT NULL DEFAULT 0 CHECK (requested_limit >= 0),
    analyzed_count INTEGER NOT NULL DEFAULT 0 CHECK (analyzed_count >= 0),
    linked_count INTEGER NOT NULL DEFAULT 0 CHECK (linked_count >= 0),
    unlinked_count INTEGER NOT NULL DEFAULT 0 CHECK (unlinked_count >= 0),
    linkable_count INTEGER NOT NULL DEFAULT 0 CHECK (linkable_count >= 0),
    non_linkable_count INTEGER NOT NULL DEFAULT 0 CHECK (non_linkable_count >= 0),
    suggested_count INTEGER NOT NULL DEFAULT 0 CHECK (suggested_count >= 0),
    safe_to_link_count INTEGER NOT NULL DEFAULT 0 CHECK (safe_to_link_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    status TEXT NOT NULL CHECK (status IN ('OK', 'PARTIAL', 'ERROR')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL
);
