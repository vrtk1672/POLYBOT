CREATE TABLE IF NOT EXISTS social_sources (
    id bigserial PRIMARY KEY,
    source_id text NOT NULL UNIQUE,
    name text NOT NULL,
    source_type text NOT NULL,
    platform text NOT NULL,
    category text NULL,
    url text NULL,
    feed_url text NULL,
    api_provider text NULL,
    enabled boolean NOT NULL DEFAULT true,
    reliability_score numeric NOT NULL DEFAULT 0.50,
    noise_baseline numeric NOT NULL DEFAULT 0.50,
    bot_risk_baseline numeric NOT NULL DEFAULT 0.50,
    last_fetch_at timestamptz NULL,
    last_success_at timestamptz NULL,
    last_error_at timestamptz NULL,
    error_count integer NOT NULL DEFAULT 0,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT social_sources_type_check CHECK (source_type IN ('RSS_MIRROR','PUBLIC_TREND_API','MANUAL','X_TWITTER','REDDIT','TELEGRAM','DISCORD','NEWS_SOCIAL_MIRROR')),
    CONSTRAINT social_sources_platform_check CHECK (platform IN ('x_twitter','reddit','telegram','discord','rss_mirror','manual','public_trends')),
    CONSTRAINT social_sources_reliability_check CHECK (reliability_score >= 0 AND reliability_score <= 1),
    CONSTRAINT social_sources_noise_check CHECK (noise_baseline >= 0 AND noise_baseline <= 1),
    CONSTRAINT social_sources_bot_check CHECK (bot_risk_baseline >= 0 AND bot_risk_baseline <= 1)
);
CREATE INDEX IF NOT EXISTS idx_social_sources_type ON social_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_social_sources_platform ON social_sources(platform);
CREATE INDEX IF NOT EXISTS idx_social_sources_category ON social_sources(category);
CREATE INDEX IF NOT EXISTS idx_social_sources_enabled ON social_sources(enabled);
CREATE INDEX IF NOT EXISTS idx_social_sources_reliability ON social_sources(reliability_score);

CREATE TABLE IF NOT EXISTS social_raw_events (
    id bigserial PRIMARY KEY,
    raw_social_event_id text NOT NULL UNIQUE,
    source_id text NOT NULL,
    platform text NOT NULL,
    external_id text NULL,
    url text NULL,
    author_id text NULL,
    author_handle text NULL,
    text text NOT NULL,
    raw_text text NULL,
    published_at timestamptz NULL,
    collected_at timestamptz NOT NULL DEFAULT now(),
    language text NULL,
    engagement_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    content_hash text NOT NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_social_raw_source ON social_raw_events(source_id);
CREATE INDEX IF NOT EXISTS idx_social_raw_platform ON social_raw_events(platform);
CREATE INDEX IF NOT EXISTS idx_social_raw_external ON social_raw_events(external_id);
CREATE INDEX IF NOT EXISTS idx_social_raw_author ON social_raw_events(author_handle);
CREATE INDEX IF NOT EXISTS idx_social_raw_hash ON social_raw_events(content_hash);
CREATE INDEX IF NOT EXISTS idx_social_raw_published ON social_raw_events(published_at);
CREATE INDEX IF NOT EXISTS idx_social_raw_collected ON social_raw_events(collected_at);

CREATE TABLE IF NOT EXISTS social_normalized_events (
    id bigserial PRIMARY KEY,
    social_event_id text NOT NULL UNIQUE,
    raw_social_event_id text NULL,
    source_id text NOT NULL,
    platform text NOT NULL,
    dedup_group_id text NULL,
    text text NOT NULL,
    normalized_text text NOT NULL,
    author_handle text NULL,
    url text NULL,
    published_at timestamptz NULL,
    collected_at timestamptz NOT NULL DEFAULT now(),
    category text NULL,
    entities_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    topics_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    hashtags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    cashtags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    language text NULL,
    engagement_score numeric NOT NULL DEFAULT 0,
    influence_score numeric NOT NULL DEFAULT 0,
    spam_score numeric NOT NULL DEFAULT 0,
    bot_risk numeric NOT NULL DEFAULT 0,
    novelty_score numeric NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'NORMALIZED',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT social_normalized_status_check CHECK (status IN ('NORMALIZED','DEDUPED','LINKED','IGNORED','SPAM','ERROR'))
);
CREATE INDEX IF NOT EXISTS idx_social_norm_source ON social_normalized_events(source_id);
CREATE INDEX IF NOT EXISTS idx_social_norm_platform ON social_normalized_events(platform);
CREATE INDEX IF NOT EXISTS idx_social_norm_dedup ON social_normalized_events(dedup_group_id);
CREATE INDEX IF NOT EXISTS idx_social_norm_category ON social_normalized_events(category);
CREATE INDEX IF NOT EXISTS idx_social_norm_published ON social_normalized_events(published_at);
CREATE INDEX IF NOT EXISTS idx_social_norm_collected ON social_normalized_events(collected_at);
CREATE INDEX IF NOT EXISTS idx_social_norm_engagement ON social_normalized_events(engagement_score);
CREATE INDEX IF NOT EXISTS idx_social_norm_spam ON social_normalized_events(spam_score);
CREATE INDEX IF NOT EXISTS idx_social_norm_bot ON social_normalized_events(bot_risk);
CREATE INDEX IF NOT EXISTS idx_social_norm_status ON social_normalized_events(status);

CREATE TABLE IF NOT EXISTS social_market_links (
    id bigserial PRIMARY KEY,
    social_link_id text NOT NULL UNIQUE,
    social_event_id text NOT NULL,
    market_id text NOT NULL,
    link_score numeric NOT NULL DEFAULT 0,
    link_reason text NULL,
    sentiment_direction text NULL,
    confidence numeric NOT NULL DEFAULT 0,
    matched_entities_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    matched_terms_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    method text NOT NULL DEFAULT 'rule_based',
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT social_market_links_direction_check CHECK (sentiment_direction IS NULL OR sentiment_direction IN ('YES','NO','UNKNOWN','BOTH','NONE'))
);
CREATE INDEX IF NOT EXISTS idx_social_links_event ON social_market_links(social_event_id);
CREATE INDEX IF NOT EXISTS idx_social_links_market ON social_market_links(market_id);
CREATE INDEX IF NOT EXISTS idx_social_links_score ON social_market_links(link_score);
CREATE INDEX IF NOT EXISTS idx_social_links_confidence ON social_market_links(confidence);
CREATE INDEX IF NOT EXISTS idx_social_links_direction ON social_market_links(sentiment_direction);
CREATE INDEX IF NOT EXISTS idx_social_links_method ON social_market_links(method);

CREATE TABLE IF NOT EXISTS social_sentiment_scores (
    id bigserial PRIMARY KEY,
    sentiment_id text NOT NULL UNIQUE,
    social_event_id text NOT NULL,
    market_id text NULL,
    sentiment text NOT NULL DEFAULT 'UNKNOWN',
    sentiment_score numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    target text NULL,
    reason text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT social_sentiment_check CHECK (sentiment IN ('YES','NO','BULLISH','BEARISH','NEUTRAL','MIXED','UNKNOWN'))
);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_event ON social_sentiment_scores(social_event_id);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_market ON social_sentiment_scores(market_id);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_sentiment ON social_sentiment_scores(sentiment);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_confidence ON social_sentiment_scores(confidence);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_created ON social_sentiment_scores(created_at);

CREATE TABLE IF NOT EXISTS social_hype_scores (
    id bigserial PRIMARY KEY,
    hype_id text NOT NULL UNIQUE,
    market_id text NOT NULL,
    window_seconds integer NOT NULL,
    mention_count integer NOT NULL DEFAULT 0,
    unique_author_count integer NOT NULL DEFAULT 0,
    mentions_velocity numeric NOT NULL DEFAULT 0,
    velocity_zscore numeric NULL,
    hype_pressure numeric NOT NULL DEFAULT 0,
    sentiment text NOT NULL DEFAULT 'UNKNOWN',
    sentiment_confidence numeric NOT NULL DEFAULT 0,
    bot_risk numeric NOT NULL DEFAULT 0,
    spam_ratio numeric NOT NULL DEFAULT 0,
    narrative_strength numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    computed_at timestamptz NOT NULL DEFAULT now(),
    signal_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_social_hype_market ON social_hype_scores(market_id);
CREATE INDEX IF NOT EXISTS idx_social_hype_computed ON social_hype_scores(computed_at);
CREATE INDEX IF NOT EXISTS idx_social_hype_pressure ON social_hype_scores(hype_pressure);
CREATE INDEX IF NOT EXISTS idx_social_hype_velocity ON social_hype_scores(mentions_velocity);
CREATE INDEX IF NOT EXISTS idx_social_hype_bot ON social_hype_scores(bot_risk);
CREATE INDEX IF NOT EXISTS idx_social_hype_confidence ON social_hype_scores(confidence);

CREATE TABLE IF NOT EXISTS social_noise_scores (
    id bigserial PRIMARY KEY,
    noise_id text NOT NULL UNIQUE,
    social_event_id text NULL,
    market_id text NULL,
    platform text NULL,
    spam_score numeric NOT NULL DEFAULT 0,
    bot_risk numeric NOT NULL DEFAULT 0,
    duplicate_risk numeric NOT NULL DEFAULT 0,
    coordinated_activity_risk numeric NOT NULL DEFAULT 0,
    noise_score numeric NOT NULL DEFAULT 0,
    reason text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_social_noise_event ON social_noise_scores(social_event_id);
CREATE INDEX IF NOT EXISTS idx_social_noise_market ON social_noise_scores(market_id);
CREATE INDEX IF NOT EXISTS idx_social_noise_platform ON social_noise_scores(platform);
CREATE INDEX IF NOT EXISTS idx_social_noise_spam ON social_noise_scores(spam_score);
CREATE INDEX IF NOT EXISTS idx_social_noise_bot ON social_noise_scores(bot_risk);
CREATE INDEX IF NOT EXISTS idx_social_noise_score ON social_noise_scores(noise_score);
CREATE INDEX IF NOT EXISTS idx_social_noise_created ON social_noise_scores(created_at);

CREATE TABLE IF NOT EXISTS social_narratives (
    id bigserial PRIMARY KEY,
    narrative_id text NOT NULL UNIQUE,
    narrative_key text NOT NULL,
    title text NOT NULL,
    topics_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    entities_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    market_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    event_count integer NOT NULL DEFAULT 0,
    narrative_strength numeric NOT NULL DEFAULT 0,
    confidence numeric NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'ACTIVE',
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT social_narratives_status_check CHECK (status IN ('ACTIVE','FADED','IGNORED','SPAM'))
);
CREATE INDEX IF NOT EXISTS idx_social_narratives_key ON social_narratives(narrative_key);
CREATE INDEX IF NOT EXISTS idx_social_narratives_status ON social_narratives(status);
CREATE INDEX IF NOT EXISTS idx_social_narratives_strength ON social_narratives(narrative_strength);
CREATE INDEX IF NOT EXISTS idx_social_narratives_first ON social_narratives(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_social_narratives_last ON social_narratives(last_seen_at);
