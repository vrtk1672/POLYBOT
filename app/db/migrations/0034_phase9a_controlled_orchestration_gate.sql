CREATE TABLE IF NOT EXISTS orchestration_gate_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')),
    orchestration_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orchestration_gate_runs_started_at
    ON orchestration_gate_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS orchestration_packets (
    id UUID PRIMARY KEY,
    orchestration_gate_run_id UUID NOT NULL REFERENCES orchestration_gate_runs(id) ON DELETE CASCADE,
    packet_status_class TEXT NOT NULL CHECK (packet_status_class IN ('DRY_RUN_READY', 'EMPTY', 'BLOCKED')),
    packet_priority_class TEXT NOT NULL CHECK (packet_priority_class IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    packet_action_count INTEGER NOT NULL DEFAULT 0,
    markets_covered_count INTEGER NOT NULL DEFAULT 0,
    included_command_intent_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    packet_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    packet_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    orchestration_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orchestration_packets_run_id
    ON orchestration_packets (orchestration_gate_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orchestration_packets_ready
    ON orchestration_packets (packet_status_class, packet_priority_class, created_at DESC);

CREATE TABLE IF NOT EXISTS orchestration_gate_records (
    id UUID PRIMARY KEY,
    orchestration_gate_run_id UUID NOT NULL REFERENCES orchestration_gate_runs(id) ON DELETE CASCADE,
    market_id TEXT NOT NULL,
    command_intent_record_id UUID NOT NULL REFERENCES command_intent_records(id) ON DELETE CASCADE,
    orchestration_decision_class TEXT NOT NULL CHECK (
        orchestration_decision_class IN (
            'ALLOW_DRY_RUN',
            'DEFER',
            'BLOCK',
            'SUPPRESS_DUPLICATE',
            'SUPPRESS_CONFLICT'
        )
    ),
    orchestration_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    orchestration_reason_text TEXT NOT NULL,
    gate_explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    packet_candidate_id UUID NULL,
    orchestration_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orchestration_gate_records_run_id
    ON orchestration_gate_records (orchestration_gate_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orchestration_gate_records_market_id
    ON orchestration_gate_records (market_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_orchestration_gate_records_decision
    ON orchestration_gate_records (orchestration_decision_class, created_at DESC);
