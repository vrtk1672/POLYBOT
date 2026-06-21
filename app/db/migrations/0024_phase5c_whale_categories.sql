CREATE TABLE IF NOT EXISTS whale_category_runs (
    id UUID PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_ref TEXT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('OPEN', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
    ),
    categorizer_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NULL,
    input_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_category_runs_started_at
    ON whale_category_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS whale_categories (
    id UUID PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    whale_profile_id UUID NOT NULL REFERENCES whale_profiles(id) ON DELETE CASCADE,
    whale_category_run_id UUID NOT NULL REFERENCES whale_category_runs(id) ON DELETE CASCADE,
    primary_category TEXT NOT NULL CHECK (
        primary_category IN (
            'SMART_WHALE', 'NOISY_WHALE', 'MOMENTUM_WHALE', 'COPY_WORTHY',
            'SPORTS_SPECIALIST', 'POLITICS_SPECIALIST', 'EVENT_SNIPER',
            'LATE_CHASER', 'UNCLASSIFIED'
        )
    ),
    secondary_categories_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    category_confidence NUMERIC(6, 5) NOT NULL,
    specialization_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    category_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    category_reason_text TEXT NOT NULL,
    explanation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    categorizer_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whale_categories_run_id
    ON whale_categories (whale_category_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_whale_categories_wallet
    ON whale_categories (wallet_address, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_whale_categories_primary
    ON whale_categories (primary_category, category_confidence DESC, created_at DESC);
