from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


def setup_source_event_tables() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_universe_memory (
                id BIGSERIAL PRIMARY KEY,
                market_memory_id TEXT NOT NULL UNIQUE,
                market_id TEXT NULL,
                condition_id TEXT NULL,
                slug TEXT NULL,
                title TEXT NULL,
                question TEXT NULL,
                category TEXT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                active BOOLEAN NOT NULL DEFAULT true,
                tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                yes_token_id TEXT NULL,
                no_token_id TEXT NULL,
                research_priority TEXT NOT NULL DEFAULT 'HIGH',
                liquidity NUMERIC NULL,
                volume NUMERIC NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_normalized_events (
                id BIGSERIAL PRIMARY KEY,
                news_event_id TEXT NOT NULL UNIQUE,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                summary TEXT NULL,
                normalized_text TEXT NULL,
                url TEXT NULL,
                published_at TIMESTAMPTZ NULL,
                collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                event_time TIMESTAMPTZ NULL,
                category TEXT NULL,
                entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                source_reliability NUMERIC NOT NULL DEFAULT 0.5,
                status TEXT NOT NULL DEFAULT 'NORMALIZED',
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_market_links (
                id BIGSERIAL PRIMARY KEY,
                link_id TEXT NOT NULL UNIQUE,
                news_event_id TEXT NOT NULL,
                market_id TEXT NOT NULL,
                link_score NUMERIC NOT NULL DEFAULT 0,
                link_reason TEXT NULL,
                direction TEXT NULL,
                confidence NUMERIC NOT NULL DEFAULT 0,
                matched_entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_terms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                method TEXT NOT NULL DEFAULT 'rule_based',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_impact_scores (
                id BIGSERIAL PRIMARY KEY,
                impact_id TEXT NOT NULL UNIQUE,
                news_event_id TEXT NOT NULL,
                market_id TEXT NOT NULL,
                direction TEXT NOT NULL DEFAULT 'UNKNOWN',
                strength NUMERIC NOT NULL DEFAULT 0,
                confidence NUMERIC NOT NULL DEFAULT 0,
                urgency NUMERIC NOT NULL DEFAULT 0,
                already_priced_in NUMERIC NOT NULL DEFAULT 0,
                ttl_seconds INTEGER NOT NULL DEFAULT 0,
                source_reliability NUMERIC NOT NULL DEFAULT 0.50,
                reason TEXT NULL,
                risk_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                signal_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_intents (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS paper_orders (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS paper_fills (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS paper_positions (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS live_orders (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS positions (id BIGSERIAL PRIMARY KEY);
            """
        )


def insert_market(
    market_id: str,
    *,
    title: str,
    entities: list[str] | None = None,
    tags: list[str] | None = None,
    keywords: list[str] | None = None,
) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO market_universe_memory (
                market_memory_id, market_id, condition_id, slug, title, question,
                category, status, active, tags_json, entities_json, keywords_json,
                yes_token_id, no_token_id, research_priority, liquidity, volume
            )
            VALUES (%s,%s,%s,%s,%s,%s,'test','ACTIVE',true,%s,%s,%s,%s,%s,'HIGH',1000,1000)
            ON CONFLICT (market_memory_id) DO UPDATE SET
                title=EXCLUDED.title,
                tags_json=EXCLUDED.tags_json,
                entities_json=EXCLUDED.entities_json,
                keywords_json=EXCLUDED.keywords_json,
                updated_at=now()
            """,
            (
                f"memory-{market_id}",
                market_id,
                f"cond-{market_id}",
                title.lower().replace(" ", "-"),
                title,
                title,
                Jsonb(tags or []),
                Jsonb(entities or []),
                Jsonb(keywords or title.lower().replace("?", "").split()),
                f"{market_id}-yes",
                f"{market_id}-no",
            ),
        )


def insert_news_event(
    event_id: str,
    *,
    title: str,
    summary: str = "",
    market_id: str | None = None,
    direction: str = "UNKNOWN",
    confidence: float = 0.0,
    already_priced_in: float | None = None,
) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO news_normalized_events (
                news_event_id, source_id, title, normalized_title, summary,
                normalized_text, published_at, collected_at, event_time,
                entities_json, topics_json, source_reliability, status
            )
            VALUES (%s,'test-rss',%s,lower(%s),%s,%s,now(),now(),now(),%s,%s,0.8,'NORMALIZED')
            """,
            (event_id, title, title, summary, summary, Jsonb([]), Jsonb(["politics"])),
        )
        if market_id:
            conn.execute(
                """
                INSERT INTO news_market_links (
                    link_id, news_event_id, market_id, link_score, direction,
                    confidence, matched_entities_json, matched_terms_json, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
                """,
                (f"link-{event_id}", event_id, market_id, confidence, direction, confidence, Jsonb([]), Jsonb(title.lower().split())),
            )
            conn.execute(
                """
                INSERT INTO news_impact_scores (
                    impact_id, news_event_id, market_id, direction, strength,
                    confidence, already_priced_in, reason
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,'fixture')
                """,
                (f"impact-{event_id}", event_id, market_id, direction, confidence, confidence, 0.5 if already_priced_in is None else already_priced_in),
            )
