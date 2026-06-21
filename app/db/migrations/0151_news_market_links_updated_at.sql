ALTER TABLE news_market_links
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE news_market_links
SET updated_at = COALESCE(updated_at, created_at, now())
WHERE updated_at IS NULL;

ALTER TABLE news_market_links
    ALTER COLUMN updated_at SET DEFAULT now();

ALTER TABLE news_market_links
    ALTER COLUMN updated_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_news_market_links_updated_at
    ON news_market_links (updated_at DESC);
