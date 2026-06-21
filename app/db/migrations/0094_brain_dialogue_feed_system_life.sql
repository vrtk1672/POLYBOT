CREATE TABLE IF NOT EXISTS brain_dialogue_events (
    id BIGSERIAL PRIMARY KEY,
    dialogue_id TEXT NOT NULL UNIQUE,
    source_event_id TEXT NULL,
    source_table TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    cycle_id TEXT NULL,
    correlation_id TEXT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    component TEXT NOT NULL,
    component_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    market_id TEXT NULL,
    candidate_id TEXT NULL,
    signal_id TEXT NULL,
    risk_decision_id TEXT NULL,
    exit_plan_id TEXT NULL,
    eligibility_id TEXT NULL,
    paper_intent_id TEXT NULL,
    paper_order_id TEXT NULL,
    paper_fill_id TEXT NULL,
    paper_position_id TEXT NULL,
    pnl_id TEXT NULL,
    inputs_received_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_used_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    agrees_with_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    conflicts_with_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    what_i_saw TEXT NULL,
    what_i_understand TEXT NULL,
    decision TEXT NULL,
    status TEXT NOT NULL,
    block_reason TEXT NULL,
    next_required_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    human_message TEXT NOT NULL,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_brain_dialogue_source_event
    ON brain_dialogue_events (source_table, source_record_id, event_type);

CREATE INDEX IF NOT EXISTS idx_brain_dialogue_timestamp
    ON brain_dialogue_events (timestamp DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_brain_dialogue_component
    ON brain_dialogue_events (component, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_brain_dialogue_market
    ON brain_dialogue_events (market_id, timestamp DESC)
    WHERE market_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_brain_dialogue_candidate
    ON brain_dialogue_events (candidate_id, timestamp DESC)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_brain_dialogue_paper_position
    ON brain_dialogue_events (paper_position_id, timestamp DESC)
    WHERE paper_position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_brain_dialogue_event_type
    ON brain_dialogue_events (event_type, timestamp DESC);
