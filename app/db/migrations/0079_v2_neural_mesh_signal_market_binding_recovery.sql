ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS link_confidence NUMERIC(10, 6) NULL CHECK (link_confidence IS NULL OR (link_confidence >= 0 AND link_confidence <= 1));

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS link_reason TEXT NULL;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS link_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS link_method TEXT NULL;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS linked_by TEXT NULL;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS is_auto_linked BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS is_review_required BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS is_runtime_link BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE signal_market_links
    ADD COLUMN IF NOT EXISTS source_signal_id TEXT NULL;

UPDATE signal_market_links
SET link_confidence = COALESCE(link_confidence, confidence),
    link_reason = COALESCE(link_reason, reason),
    linked_by = COALESCE(linked_by, created_by),
    source_signal_id = COALESCE(source_signal_id, signal_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_market_links_unique_signal_market
    ON signal_market_links (signal_id, market_id);

CREATE INDEX IF NOT EXISTS idx_signal_market_links_method
    ON signal_market_links (link_method)
    WHERE link_method IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_market_links_auto
    ON signal_market_links (is_auto_linked);

CREATE INDEX IF NOT EXISTS idx_signal_market_links_runtime
    ON signal_market_links (is_runtime_link);

CREATE TABLE IF NOT EXISTS signal_market_binding_recovery_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    signals_checked INTEGER NOT NULL DEFAULT 0 CHECK (signals_checked >= 0),
    runtime_signals_checked INTEGER NOT NULL DEFAULT 0 CHECK (runtime_signals_checked >= 0),
    already_linked INTEGER NOT NULL DEFAULT 0 CHECK (already_linked >= 0),
    safe_links_created INTEGER NOT NULL DEFAULT 0 CHECK (safe_links_created >= 0),
    suggestions_created INTEGER NOT NULL DEFAULT 0 CHECK (suggestions_created >= 0),
    remained_unlinked INTEGER NOT NULL DEFAULT 0 CHECK (remained_unlinked >= 0),
    stale_skipped INTEGER NOT NULL DEFAULT 0 CHECK (stale_skipped >= 0),
    dry_run_skipped INTEGER NOT NULL DEFAULT 0 CHECK (dry_run_skipped >= 0),
    weak_evidence_skipped INTEGER NOT NULL DEFAULT 0 CHECK (weak_evidence_skipped >= 0),
    ambiguous_candidates INTEGER NOT NULL DEFAULT 0 CHECK (ambiguous_candidates >= 0),
    signal_market_links_before INTEGER NOT NULL DEFAULT 0 CHECK (signal_market_links_before >= 0),
    signal_market_links_after INTEGER NOT NULL DEFAULT 0 CHECK (signal_market_links_after >= 0),
    paper_ready_before BOOLEAN NOT NULL DEFAULT FALSE,
    paper_ready_after BOOLEAN NOT NULL DEFAULT FALSE,
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

CREATE INDEX IF NOT EXISTS idx_signal_market_binding_runs_created
    ON signal_market_binding_recovery_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_market_binding_runs_status
    ON signal_market_binding_recovery_runs (status);

CREATE TABLE IF NOT EXISTS signal_market_binding_candidates (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL REFERENCES neuron_signals(signal_id) ON DELETE CASCADE,
    candidate_market_id TEXT NULL,
    confidence NUMERIC(10, 6) NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN (
            'AUTO_LINKED',
            'REVIEW_ONLY',
            'BLOCKED_WEAK_EVIDENCE',
            'BLOCKED_STALE',
            'BLOCKED_DRY_RUN',
            'BLOCKED_MISSING_MARKET',
            'BLOCKED_AMBIGUOUS',
            'ERROR'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signal_market_binding_candidates_run
    ON signal_market_binding_candidates (run_id);

CREATE INDEX IF NOT EXISTS idx_signal_market_binding_candidates_signal
    ON signal_market_binding_candidates (signal_id);

CREATE INDEX IF NOT EXISTS idx_signal_market_binding_candidates_market
    ON signal_market_binding_candidates (candidate_market_id)
    WHERE candidate_market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_signal_market_binding_candidates_action
    ON signal_market_binding_candidates (action);

