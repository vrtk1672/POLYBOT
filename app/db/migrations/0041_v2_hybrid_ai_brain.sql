CREATE TABLE IF NOT EXISTS ai_prompt_versions (
    id bigserial PRIMARY KEY,
    prompt_version_id text NOT NULL UNIQUE,
    prompt_name text NOT NULL,
    prompt_type text NOT NULL,
    model_family text NULL,
    version text NOT NULL,
    template_text text NOT NULL,
    schema_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ai_prompt_versions_prompt_name ON ai_prompt_versions(prompt_name);
CREATE INDEX IF NOT EXISTS idx_ai_prompt_versions_prompt_type ON ai_prompt_versions(prompt_type);
CREATE INDEX IF NOT EXISTS idx_ai_prompt_versions_active ON ai_prompt_versions(active);

CREATE TABLE IF NOT EXISTS ai_requests (
    id bigserial PRIMARY KEY,
    ai_request_id text NOT NULL UNIQUE,
    request_hash text NOT NULL,
    market_id text NULL,
    event_id text NULL,
    correlation_id text NOT NULL,
    source_service text NOT NULL,
    task_type text NOT NULL,
    model_route text NOT NULL,
    selected_model text NULL,
    prompt_version_id text NULL,
    cache_key text NULL,
    cache_hit boolean NOT NULL DEFAULT false,
    budget_allowed boolean NOT NULL DEFAULT false,
    escalation_requested boolean NOT NULL DEFAULT false,
    escalation_allowed boolean NOT NULL DEFAULT false,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    latency_ms integer NULL,
    input_tokens integer NULL,
    output_tokens integer NULL,
    estimated_cost numeric NOT NULL DEFAULT 0,
    error_message text NULL,
    request_metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ai_requests_status_check CHECK (status IN ('PENDING','CACHE_HIT','BUDGET_BLOCKED','LOCAL_COMPLETED','CLOUD_COMPLETED','FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_ai_requests_request_hash ON ai_requests(request_hash);
CREATE INDEX IF NOT EXISTS idx_ai_requests_market_id ON ai_requests(market_id);
CREATE INDEX IF NOT EXISTS idx_ai_requests_correlation_id ON ai_requests(correlation_id);
CREATE INDEX IF NOT EXISTS idx_ai_requests_task_type ON ai_requests(task_type);
CREATE INDEX IF NOT EXISTS idx_ai_requests_selected_model ON ai_requests(selected_model);
CREATE INDEX IF NOT EXISTS idx_ai_requests_status ON ai_requests(status);
CREATE INDEX IF NOT EXISTS idx_ai_requests_created_at ON ai_requests(created_at);

CREATE TABLE IF NOT EXISTS ai_responses (
    id bigserial PRIMARY KEY,
    ai_response_id text NOT NULL UNIQUE,
    ai_request_id text NOT NULL,
    response_hash text NOT NULL,
    model_name text NOT NULL,
    task_type text NOT NULL,
    structured_output_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_output_redacted text NULL,
    confidence numeric NULL,
    recommended_action text NULL,
    risk_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ai_responses_ai_request_id ON ai_responses(ai_request_id);
CREATE INDEX IF NOT EXISTS idx_ai_responses_response_hash ON ai_responses(response_hash);
CREATE INDEX IF NOT EXISTS idx_ai_responses_task_type ON ai_responses(task_type);
CREATE INDEX IF NOT EXISTS idx_ai_responses_confidence ON ai_responses(confidence);

CREATE TABLE IF NOT EXISTS ai_cache (
    id bigserial PRIMARY KEY,
    cache_key text NOT NULL UNIQUE,
    request_hash text NOT NULL,
    task_type text NOT NULL,
    market_id text NULL,
    prompt_version_id text NULL,
    model_name text NULL,
    response_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    confidence numeric NULL,
    expires_at timestamptz NULL,
    hit_count integer NOT NULL DEFAULT 0,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_hit_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ai_cache_request_hash ON ai_cache(request_hash);
CREATE INDEX IF NOT EXISTS idx_ai_cache_task_type ON ai_cache(task_type);
CREATE INDEX IF NOT EXISTS idx_ai_cache_market_id ON ai_cache(market_id);
CREATE INDEX IF NOT EXISTS idx_ai_cache_expires_at ON ai_cache(expires_at);

CREATE TABLE IF NOT EXISTS ai_cost_ledger (
    id bigserial PRIMARY KEY,
    cost_id text NOT NULL UNIQUE,
    ai_request_id text NULL,
    model_name text NOT NULL,
    provider text NOT NULL,
    task_type text NOT NULL,
    input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    estimated_cost numeric NOT NULL DEFAULT 0,
    actual_cost numeric NULL,
    currency text NOT NULL DEFAULT 'USD',
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ai_cost_ledger_ai_request_id ON ai_cost_ledger(ai_request_id);
CREATE INDEX IF NOT EXISTS idx_ai_cost_ledger_model_name ON ai_cost_ledger(model_name);
CREATE INDEX IF NOT EXISTS idx_ai_cost_ledger_provider ON ai_cost_ledger(provider);
CREATE INDEX IF NOT EXISTS idx_ai_cost_ledger_task_type ON ai_cost_ledger(task_type);
CREATE INDEX IF NOT EXISTS idx_ai_cost_ledger_created_at ON ai_cost_ledger(created_at);

CREATE TABLE IF NOT EXISTS ai_escalations (
    id bigserial PRIMARY KEY,
    escalation_id text NOT NULL UNIQUE,
    ai_request_id text NOT NULL,
    market_id text NULL,
    task_type text NOT NULL,
    from_model text NULL,
    to_model text NOT NULL,
    reason text NOT NULL,
    local_confidence numeric NULL,
    escalation_allowed boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'PENDING',
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ai_escalations_status_check CHECK (status IN ('PENDING','APPROVED','BLOCKED','COMPLETED','FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_ai_escalations_ai_request_id ON ai_escalations(ai_request_id);
CREATE INDEX IF NOT EXISTS idx_ai_escalations_market_id ON ai_escalations(market_id);
CREATE INDEX IF NOT EXISTS idx_ai_escalations_status ON ai_escalations(status);
CREATE INDEX IF NOT EXISTS idx_ai_escalations_created_at ON ai_escalations(created_at);

CREATE TABLE IF NOT EXISTS ai_decision_logs (
    id bigserial PRIMARY KEY,
    ai_decision_id text NOT NULL UNIQUE,
    ai_request_id text NULL,
    market_id text NULL,
    event_id text NULL,
    correlation_id text NOT NULL,
    task_type text NOT NULL,
    decision_type text NOT NULL,
    output_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    confidence numeric NULL,
    risk_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    cannot_trade_reason text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_ai_request_id ON ai_decision_logs(ai_request_id);
CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_market_id ON ai_decision_logs(market_id);
CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_task_type ON ai_decision_logs(task_type);
CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_decision_type ON ai_decision_logs(decision_type);
CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_confidence ON ai_decision_logs(confidence);
CREATE INDEX IF NOT EXISTS idx_ai_decision_logs_created_at ON ai_decision_logs(created_at);

CREATE TABLE IF NOT EXISTS ai_model_performance (
    id bigserial PRIMARY KEY,
    model_name text NOT NULL,
    provider text NOT NULL,
    task_type text NOT NULL,
    total_requests integer NOT NULL DEFAULT 0,
    cache_hits integer NOT NULL DEFAULT 0,
    failures integer NOT NULL DEFAULT 0,
    escalations integer NOT NULL DEFAULT 0,
    avg_latency_ms numeric NULL,
    avg_confidence numeric NULL,
    estimated_total_cost numeric NOT NULL DEFAULT 0,
    usefulness_score numeric NULL,
    last_updated_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ai_model_performance_unique UNIQUE (model_name, provider, task_type)
);

CREATE INDEX IF NOT EXISTS idx_ai_model_performance_model_name ON ai_model_performance(model_name);
CREATE INDEX IF NOT EXISTS idx_ai_model_performance_provider ON ai_model_performance(provider);
CREATE INDEX IF NOT EXISTS idx_ai_model_performance_task_type ON ai_model_performance(task_type);
CREATE INDEX IF NOT EXISTS idx_ai_model_performance_usefulness ON ai_model_performance(usefulness_score);
