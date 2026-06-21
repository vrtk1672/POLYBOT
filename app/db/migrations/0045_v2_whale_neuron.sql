CREATE TABLE IF NOT EXISTS whale_sources (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL UNIQUE,
    name text NOT NULL,
    source_type text NOT NULL,
    platform text NULL,
    url text NULL,
    enabled boolean NOT NULL DEFAULT true,
    reliability_score numeric NOT NULL DEFAULT 0.50,
    last_fetch_at timestamptz NULL,
    last_success_at timestamptz NULL,
    last_error_at timestamptz NULL,
    error_count integer NOT NULL DEFAULT 0,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT whale_sources_type_v27_check CHECK (source_type IN ('POLYMARKET_PUBLIC','CLOB_PUBLIC','MANUAL','INTERNAL_PAPER','CHAIN','API','CSV_IMPORT','MOCK')),
    CONSTRAINT whale_sources_reliability_v27_check CHECK (reliability_score >= 0 AND reliability_score <= 1)
);
CREATE INDEX IF NOT EXISTS idx_whale_sources_v27_type ON whale_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_whale_sources_v27_enabled ON whale_sources(enabled);
CREATE INDEX IF NOT EXISTS idx_whale_sources_v27_reliability ON whale_sources(reliability_score);

ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS whale_event_id text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS source_id text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS whale_id text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS trader_label text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS asset_id text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS side text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS action_type text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS size_usd numeric;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS size_shares numeric;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS tx_hash text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS order_id text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS event_time timestamptz;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS raw_event_json jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS normalized_event_json jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS event_classification text;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS confidence numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_events ADD COLUMN IF NOT EXISTS metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb;
UPDATE whale_events SET whale_event_id = id::text WHERE whale_event_id IS NULL;
UPDATE whale_events SET whale_id = COALESCE(wallet_address, id::text) WHERE whale_id IS NULL;
UPDATE whale_events SET source_id = COALESCE(source_type, 'legacy') WHERE source_id IS NULL;
UPDATE whale_events SET side = COALESCE(side_or_outcome, 'UNKNOWN') WHERE side IS NULL;
UPDATE whale_events SET action_type = 'UNKNOWN' WHERE action_type IS NULL;
UPDATE whale_events SET size_usd = COALESCE(notional, size, 0) WHERE size_usd IS NULL;
UPDATE whale_events SET size_shares = size WHERE size_shares IS NULL;
UPDATE whale_events SET event_time = event_timestamp WHERE event_time IS NULL;
UPDATE whale_events SET event_classification = event_direction_class WHERE event_classification IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_whale_events_v27_event_id ON whale_events(whale_event_id);
CREATE INDEX IF NOT EXISTS idx_whale_events_v27_whale_id ON whale_events(whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_events_v27_side ON whale_events(side);
CREATE INDEX IF NOT EXISTS idx_whale_events_v27_action_type ON whale_events(action_type);
CREATE INDEX IF NOT EXISTS idx_whale_events_v27_classification ON whale_events(event_classification);
CREATE INDEX IF NOT EXISTS idx_whale_events_v27_size_usd ON whale_events(size_usd);

ALTER TABLE whale_registry ADD COLUMN IF NOT EXISTS whale_id text;
ALTER TABLE whale_registry ADD COLUMN IF NOT EXISTS display_label text;
ALTER TABLE whale_registry ADD COLUMN IF NOT EXISTS total_notional_usd numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_registry ADD COLUMN IF NOT EXISTS known_market_families_json jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE whale_registry ADD COLUMN IF NOT EXISTS status text;
UPDATE whale_registry SET whale_id = COALESCE(wallet_address, id::text) WHERE whale_id IS NULL;
UPDATE whale_registry SET status = CASE WHEN registry_status = 'IGNORE' THEN 'IGNORED' ELSE COALESCE(registry_status, 'ACTIVE') END WHERE status IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_whale_registry_v27_whale_id ON whale_registry(whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_registry_v27_total_notional ON whale_registry(total_notional_usd);
CREATE INDEX IF NOT EXISTS idx_whale_registry_v27_status ON whale_registry(status);

ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS whale_profile_id text;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS whale_id text;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS profile_version text NOT NULL DEFAULT 'v2.7';
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS hit_rate numeric;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS timing_quality numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS average_entry_quality numeric;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS average_exit_quality numeric;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS average_hold_time_seconds numeric;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS average_trade_size_usd numeric;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS win_consistency numeric;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS market_specialties_v27_json jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS follow_value numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS momentum_chase_score numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS reversal_risk_score numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS copy_worthy_score numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS confidence numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS sample_size integer NOT NULL DEFAULT 0;
ALTER TABLE whale_profiles ADD COLUMN IF NOT EXISTS last_updated_at timestamptz NOT NULL DEFAULT now();
UPDATE whale_profiles SET whale_profile_id = id::text WHERE whale_profile_id IS NULL;
UPDATE whale_profiles SET whale_id = wallet_address WHERE whale_id IS NULL;
UPDATE whale_profiles SET timing_quality = timing_consistency_score WHERE timing_quality = 0;
UPDATE whale_profiles SET average_trade_size_usd = COALESCE(average_notional, average_size) WHERE average_trade_size_usd IS NULL;
UPDATE whale_profiles SET follow_value = follow_value_baseline WHERE follow_value = 0;
UPDATE whale_profiles SET sample_size = total_events WHERE sample_size = 0;
CREATE UNIQUE INDEX IF NOT EXISTS idx_whale_profiles_v27_profile_id ON whale_profiles(whale_profile_id);
CREATE INDEX IF NOT EXISTS idx_whale_profiles_v27_whale_id ON whale_profiles(whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_profiles_v27_follow ON whale_profiles(follow_value);
CREATE INDEX IF NOT EXISTS idx_whale_profiles_v27_copy ON whale_profiles(copy_worthy_score);

ALTER TABLE whale_categories ADD COLUMN IF NOT EXISTS whale_category_id text;
ALTER TABLE whale_categories ADD COLUMN IF NOT EXISTS whale_id text;
ALTER TABLE whale_categories ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE whale_categories ADD COLUMN IF NOT EXISTS score numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_categories ADD COLUMN IF NOT EXISTS confidence numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_categories ADD COLUMN IF NOT EXISTS reason text;
ALTER TABLE whale_categories ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;
UPDATE whale_categories SET whale_category_id = id::text WHERE whale_category_id IS NULL;
UPDATE whale_categories SET whale_id = wallet_address WHERE whale_id IS NULL;
UPDATE whale_categories SET category = lower(primary_category) WHERE category IS NULL;
UPDATE whale_categories SET confidence = category_confidence WHERE confidence = 0;
UPDATE whale_categories SET reason = category_reason_text WHERE reason IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_whale_categories_v27_category_id ON whale_categories(whale_category_id);
CREATE INDEX IF NOT EXISTS idx_whale_categories_v27_whale_id ON whale_categories(whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_categories_v27_category ON whale_categories(category);
CREATE INDEX IF NOT EXISTS idx_whale_categories_v27_active ON whale_categories(active);

ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS whale_market_score_id text;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS whale_id text;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS whale_event_id text;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS side text;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS smart_whale_alignment numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS follow_value numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS noise_penalty numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS confidence numeric NOT NULL DEFAULT 0;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS signal_json jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS computed_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE whale_market_scores ADD COLUMN IF NOT EXISTS metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb;
UPDATE whale_market_scores SET whale_market_score_id = id::text WHERE whale_market_score_id IS NULL;
UPDATE whale_market_scores SET smart_whale_alignment = smart_whale_alignment_score WHERE smart_whale_alignment = 0;
UPDATE whale_market_scores SET computed_at = created_at WHERE computed_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_whale_market_scores_v27_score_id ON whale_market_scores(whale_market_score_id);
CREATE INDEX IF NOT EXISTS idx_whale_market_scores_v27_whale ON whale_market_scores(whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_market_scores_v27_follow ON whale_market_scores(follow_value);
CREATE INDEX IF NOT EXISTS idx_whale_market_scores_v27_noise ON whale_market_scores(noise_penalty);

CREATE TABLE IF NOT EXISTS whale_performance_history (
    id bigserial PRIMARY KEY,
    whale_performance_id text NOT NULL UNIQUE,
    whale_id text NOT NULL,
    market_id text NULL,
    whale_event_id text NULL,
    observed_outcome text NULL,
    pnl_proxy numeric NULL,
    timing_quality numeric NULL,
    entry_quality numeric NULL,
    exit_quality numeric NULL,
    was_early boolean NULL,
    was_late boolean NULL,
    was_noisy boolean NULL,
    follow_result text NOT NULL DEFAULT 'INSUFFICIENT_DATA',
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT whale_performance_follow_result_v27_check CHECK (follow_result IN ('GOOD_FOLLOW','BAD_FOLLOW','NEUTRAL','INSUFFICIENT_DATA'))
);
CREATE INDEX IF NOT EXISTS idx_whale_perf_v27_whale ON whale_performance_history(whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_perf_v27_market ON whale_performance_history(market_id);
CREATE INDEX IF NOT EXISTS idx_whale_perf_v27_result ON whale_performance_history(follow_result);
CREATE INDEX IF NOT EXISTS idx_whale_perf_v27_evaluated ON whale_performance_history(evaluated_at);

CREATE TABLE IF NOT EXISTS whale_follow_decisions (
    id bigserial PRIMARY KEY,
    whale_follow_decision_id text NOT NULL UNIQUE,
    whale_id text NOT NULL,
    market_id text NULL,
    whale_event_id text NULL,
    decision text NOT NULL,
    follow_value numeric NOT NULL DEFAULT 0,
    noise_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    reason text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT whale_follow_decision_v27_check CHECK (decision IN ('FOLLOW','WATCH','IGNORE','PENALIZE','INSUFFICIENT_DATA'))
);
CREATE INDEX IF NOT EXISTS idx_whale_follow_v27_whale ON whale_follow_decisions(whale_id);
CREATE INDEX IF NOT EXISTS idx_whale_follow_v27_market ON whale_follow_decisions(market_id);
CREATE INDEX IF NOT EXISTS idx_whale_follow_v27_decision ON whale_follow_decisions(decision);
CREATE INDEX IF NOT EXISTS idx_whale_follow_v27_created ON whale_follow_decisions(created_at);
