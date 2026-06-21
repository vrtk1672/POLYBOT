CREATE TABLE IF NOT EXISTS news_sources (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL UNIQUE,
    name text NOT NULL,
    source_type text NOT NULL,
    category text NULL,
    region text NULL,
    url text NULL,
    feed_url text NULL,
    api_provider text NULL,
    enabled boolean NOT NULL DEFAULT true,
    reliability_score numeric NOT NULL DEFAULT 0.50,
    latency_score numeric NULL,
    bias_notes text NULL,
    last_fetch_at timestamptz NULL,
    last_success_at timestamptz NULL,
    last_error_at timestamptz NULL,
    error_count integer NOT NULL DEFAULT 0,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT news_sources_type_check CHECK (source_type IN ('RSS','API','WEB','MANUAL','POLYMARKET','COURT','WEATHER','SPORTS','CRYPTO','MACRO','SECURITY','GEO_POLITICS')),
    CONSTRAINT news_sources_reliability_check CHECK (reliability_score >= 0 AND reliability_score <= 1)
);
CREATE INDEX IF NOT EXISTS idx_news_sources_type ON news_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_news_sources_category ON news_sources(category);
CREATE INDEX IF NOT EXISTS idx_news_sources_enabled ON news_sources(enabled);
CREATE INDEX IF NOT EXISTS idx_news_sources_reliability ON news_sources(reliability_score);

CREATE TABLE IF NOT EXISTS news_raw_events (
    id bigserial PRIMARY KEY,
    raw_event_id text NOT NULL UNIQUE,
    source_id text NOT NULL,
    external_id text NULL,
    url text NULL,
    title text NOT NULL,
    summary text NULL,
    body_text text NULL,
    author text NULL,
    published_at timestamptz NULL,
    collected_at timestamptz NOT NULL DEFAULT now(),
    language text NULL,
    raw_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    content_hash text NOT NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_news_raw_source ON news_raw_events(source_id);
CREATE INDEX IF NOT EXISTS idx_news_raw_external ON news_raw_events(external_id);
CREATE INDEX IF NOT EXISTS idx_news_raw_hash ON news_raw_events(content_hash);
CREATE INDEX IF NOT EXISTS idx_news_raw_published ON news_raw_events(published_at);
CREATE INDEX IF NOT EXISTS idx_news_raw_collected ON news_raw_events(collected_at);

CREATE TABLE IF NOT EXISTS news_normalized_events (
    id bigserial PRIMARY KEY,
    news_event_id text NOT NULL UNIQUE,
    raw_event_id text NULL,
    source_id text NOT NULL,
    dedup_group_id text NULL,
    title text NOT NULL,
    normalized_title text NOT NULL,
    summary text NULL,
    normalized_text text NULL,
    url text NULL,
    published_at timestamptz NULL,
    collected_at timestamptz NOT NULL DEFAULT now(),
    event_time timestamptz NULL,
    category text NULL,
    entities_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    topics_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    language text NULL,
    importance_score numeric NOT NULL DEFAULT 0,
    urgency_score numeric NOT NULL DEFAULT 0,
    novelty_score numeric NOT NULL DEFAULT 0,
    source_reliability numeric NOT NULL DEFAULT 0.50,
    status text NOT NULL DEFAULT 'NORMALIZED',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT news_normalized_status_check CHECK (status IN ('NORMALIZED','DEDUPED','LINKED','IGNORED','ERROR'))
);
CREATE INDEX IF NOT EXISTS idx_news_norm_source ON news_normalized_events(source_id);
CREATE INDEX IF NOT EXISTS idx_news_norm_dedup ON news_normalized_events(dedup_group_id);
CREATE INDEX IF NOT EXISTS idx_news_norm_category ON news_normalized_events(category);
CREATE INDEX IF NOT EXISTS idx_news_norm_published ON news_normalized_events(published_at);
CREATE INDEX IF NOT EXISTS idx_news_norm_collected ON news_normalized_events(collected_at);
CREATE INDEX IF NOT EXISTS idx_news_norm_importance ON news_normalized_events(importance_score);
CREATE INDEX IF NOT EXISTS idx_news_norm_urgency ON news_normalized_events(urgency_score);
CREATE INDEX IF NOT EXISTS idx_news_norm_novelty ON news_normalized_events(novelty_score);
CREATE INDEX IF NOT EXISTS idx_news_norm_status ON news_normalized_events(status);

CREATE TABLE IF NOT EXISTS news_dedup_groups (
    id bigserial PRIMARY KEY,
    dedup_group_id text NOT NULL UNIQUE,
    canonical_news_event_id text NULL,
    group_hash text NOT NULL,
    normalized_title text NULL,
    topic_signature text NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    event_count integer NOT NULL DEFAULT 0,
    sources_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_news_dedup_hash ON news_dedup_groups(group_hash);
CREATE INDEX IF NOT EXISTS idx_news_dedup_first ON news_dedup_groups(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_news_dedup_last ON news_dedup_groups(last_seen_at);

CREATE TABLE IF NOT EXISTS news_market_links (
    id bigserial PRIMARY KEY,
    link_id text NOT NULL UNIQUE,
    news_event_id text NOT NULL,
    market_id text NOT NULL,
    link_score numeric NOT NULL DEFAULT 0,
    link_reason text NULL,
    direction text NULL,
    confidence numeric NOT NULL DEFAULT 0,
    matched_entities_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    matched_terms_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    method text NOT NULL DEFAULT 'rule_based',
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT news_market_links_direction_check CHECK (direction IS NULL OR direction IN ('YES','NO','UNKNOWN','BOTH','NONE'))
);
CREATE INDEX IF NOT EXISTS idx_news_links_event ON news_market_links(news_event_id);
CREATE INDEX IF NOT EXISTS idx_news_links_market ON news_market_links(market_id);
CREATE INDEX IF NOT EXISTS idx_news_links_score ON news_market_links(link_score);
CREATE INDEX IF NOT EXISTS idx_news_links_confidence ON news_market_links(confidence);
CREATE INDEX IF NOT EXISTS idx_news_links_direction ON news_market_links(direction);
CREATE INDEX IF NOT EXISTS idx_news_links_method ON news_market_links(method);

CREATE TABLE IF NOT EXISTS news_impact_scores (
    id bigserial PRIMARY KEY,
    impact_id text NOT NULL UNIQUE,
    news_event_id text NOT NULL,
    market_id text NOT NULL,
    direction text NOT NULL DEFAULT 'UNKNOWN',
    strength numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    urgency numeric NOT NULL DEFAULT 0,
    already_priced_in numeric NOT NULL DEFAULT 0,
    ttl_seconds integer NOT NULL DEFAULT 0,
    source_reliability numeric NOT NULL DEFAULT 0.50,
    reason text NULL,
    risk_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    signal_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT news_impact_direction_check CHECK (direction IN ('YES','NO','UNKNOWN','BOTH','NONE'))
);
CREATE INDEX IF NOT EXISTS idx_news_impact_event ON news_impact_scores(news_event_id);
CREATE INDEX IF NOT EXISTS idx_news_impact_market ON news_impact_scores(market_id);
CREATE INDEX IF NOT EXISTS idx_news_impact_strength ON news_impact_scores(strength);
CREATE INDEX IF NOT EXISTS idx_news_impact_confidence ON news_impact_scores(confidence);
CREATE INDEX IF NOT EXISTS idx_news_impact_urgency ON news_impact_scores(urgency);
CREATE INDEX IF NOT EXISTS idx_news_impact_priced ON news_impact_scores(already_priced_in);
CREATE INDEX IF NOT EXISTS idx_news_impact_created ON news_impact_scores(created_at);

CREATE TABLE IF NOT EXISTS news_source_reliability (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL,
    category text NULL,
    total_events integer NOT NULL DEFAULT 0,
    linked_events integer NOT NULL DEFAULT 0,
    ignored_events integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    avg_latency_seconds numeric NULL,
    avg_impact_score numeric NULL,
    reliability_score numeric NOT NULL DEFAULT 0.50,
    last_updated_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT news_source_reliability_unique UNIQUE (source_id, category)
);
CREATE INDEX IF NOT EXISTS idx_news_reliability_source ON news_source_reliability(source_id);
CREATE INDEX IF NOT EXISTS idx_news_reliability_category ON news_source_reliability(category);
CREATE INDEX IF NOT EXISTS idx_news_reliability_score ON news_source_reliability(reliability_score);

CREATE TABLE IF NOT EXISTS news_ai_analysis (
    id bigserial PRIMARY KEY,
    news_ai_analysis_id text NOT NULL UNIQUE,
    news_event_id text NOT NULL,
    market_id text NULL,
    ai_request_id text NULL,
    task_type text NOT NULL,
    analysis_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    confidence numeric NULL,
    risk_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_news_ai_analysis_event ON news_ai_analysis(news_event_id);
CREATE INDEX IF NOT EXISTS idx_news_ai_analysis_market ON news_ai_analysis(market_id);
CREATE INDEX IF NOT EXISTS idx_news_ai_analysis_request ON news_ai_analysis(ai_request_id);
CREATE INDEX IF NOT EXISTS idx_news_ai_analysis_task ON news_ai_analysis(task_type);
CREATE INDEX IF NOT EXISTS idx_news_ai_analysis_confidence ON news_ai_analysis(confidence);
