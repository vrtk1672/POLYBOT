CREATE TABLE IF NOT EXISTS thesis_profiles (
    id BIGSERIAL PRIMARY KEY,
    thesis_id TEXT NOT NULL UNIQUE,
    market_id TEXT NULL,
    side TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('COMPLETE', 'INCOMPLETE', 'BLOCKED', 'WEAK', 'ERROR')),
    thesis_type TEXT NOT NULL CHECK (
        thesis_type IN (
            'RUNTIME_COORDINATOR_THESIS',
            'BLOCKED_NO_TRADE_THESIS',
            'HOLD_FOR_MORE_EVIDENCE',
            'WEAK_SIGNAL_THESIS'
        )
    ),
    why_now TEXT NOT NULL CHECK (length(trim(why_now)) > 0),
    expected_move TEXT NULL,
    confidence NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    invalidation_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_notes JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_coordinator_decision_id TEXT NULL,
    source_brain_output_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_signal_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    orderbook_snapshot_id BIGINT NULL,
    generated_by TEXT NOT NULL DEFAULT 'runtime',
    producer_name TEXT NOT NULL DEFAULT 'thesis_profile_builder',
    is_runtime_generated BOOLEAN NOT NULL DEFAULT true,
    is_dry_run_generated BOOLEAN NOT NULL DEFAULT false,
    paper_candidate_allowed BOOLEAN NOT NULL DEFAULT false CHECK (paper_candidate_allowed = false),
    risk_required BOOLEAN NOT NULL DEFAULT true,
    exit_required BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_thesis_profiles_market
    ON thesis_profiles (market_id)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_thesis_profiles_status
    ON thesis_profiles (status);

CREATE INDEX IF NOT EXISTS idx_thesis_profiles_type
    ON thesis_profiles (thesis_type);

CREATE INDEX IF NOT EXISTS idx_thesis_profiles_coordinator
    ON thesis_profiles (source_coordinator_decision_id)
    WHERE source_coordinator_decision_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_thesis_profiles_runtime
    ON thesis_profiles (is_runtime_generated);

CREATE INDEX IF NOT EXISTS idx_thesis_profiles_created
    ON thesis_profiles (created_at DESC);

CREATE TABLE IF NOT EXISTS thesis_profile_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    coordinator_decisions_checked INTEGER NOT NULL DEFAULT 0 CHECK (coordinator_decisions_checked >= 0),
    eligible_decisions INTEGER NOT NULL DEFAULT 0 CHECK (eligible_decisions >= 0),
    thesis_profiles_created INTEGER NOT NULL DEFAULT 0 CHECK (thesis_profiles_created >= 0),
    thesis_profiles_updated INTEGER NOT NULL DEFAULT 0 CHECK (thesis_profiles_updated >= 0),
    complete_thesis_count INTEGER NOT NULL DEFAULT 0 CHECK (complete_thesis_count >= 0),
    incomplete_thesis_count INTEGER NOT NULL DEFAULT 0 CHECK (incomplete_thesis_count >= 0),
    blocked_thesis_count INTEGER NOT NULL DEFAULT 0 CHECK (blocked_thesis_count >= 0),
    weak_thesis_count INTEGER NOT NULL DEFAULT 0 CHECK (weak_thesis_count >= 0),
    missing_market_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_market_count >= 0),
    missing_orderbook_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_orderbook_count >= 0),
    missing_binding_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_binding_count >= 0),
    missing_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_evidence_count >= 0),
    paper_ready_before BOOLEAN NOT NULL DEFAULT false,
    paper_ready_after BOOLEAN NOT NULL DEFAULT false,
    orders_created INTEGER NOT NULL DEFAULT 0 CHECK (orders_created >= 0),
    order_intents_created INTEGER NOT NULL DEFAULT 0 CHECK (order_intents_created >= 0),
    fills_created INTEGER NOT NULL DEFAULT 0 CHECK (fills_created >= 0),
    positions_created INTEGER NOT NULL DEFAULT 0 CHECK (positions_created >= 0),
    live_actions_created INTEGER NOT NULL DEFAULT 0 CHECK (live_actions_created >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    error_summary TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_thesis_profile_runs_created
    ON thesis_profile_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_thesis_profile_runs_status
    ON thesis_profile_runs (status);

CREATE TABLE IF NOT EXISTS thesis_profile_evidence_items (
    id BIGSERIAL PRIMARY KEY,
    thesis_id TEXT NOT NULL REFERENCES thesis_profiles(thesis_id) ON DELETE CASCADE,
    evidence_type TEXT NOT NULL,
    source_id TEXT NULL,
    source_type TEXT NULL,
    confidence NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_thesis_profile_evidence_thesis
    ON thesis_profile_evidence_items (thesis_id);

CREATE INDEX IF NOT EXISTS idx_thesis_profile_evidence_type
    ON thesis_profile_evidence_items (evidence_type);
