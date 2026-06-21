from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


def setup_market_tables() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS markets_v2 (
                id BIGSERIAL PRIMARY KEY,
                market_id TEXT UNIQUE,
                condition_id TEXT NULL,
                question TEXT NULL,
                slug TEXT NULL,
                category TEXT NULL,
                market_family TEXT NULL,
                yes_token_id TEXT NULL,
                no_token_id TEXT NULL,
                outcome_tokens_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                source TEXT NOT NULL DEFAULT 'polymarket',
                accepting_orders BOOLEAN NULL,
                closed BOOLEAN NOT NULL DEFAULT false,
                archived BOOLEAN NOT NULL DEFAULT false,
                active BOOLEAN NOT NULL DEFAULT true,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                close_time TIMESTAMPTZ NULL,
                resolution_time TIMESTAMPTZ NULL,
                raw_market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots_v2 (
                id BIGSERIAL PRIMARY KEY,
                market_id TEXT NOT NULL,
                current_price_yes NUMERIC NULL,
                current_price_no NUMERIC NULL,
                best_bid NUMERIC NULL,
                best_ask NUMERIC NULL,
                spread NUMERIC NULL,
                volume_24h NUMERIC NULL,
                liquidity NUMERIC NULL,
                snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                id BIGSERIAL PRIMARY KEY,
                orderbook_snapshot_id TEXT NULL,
                market_id TEXT NOT NULL,
                token_id TEXT NULL,
                side TEXT NULL,
                best_bid NUMERIC NULL,
                best_ask NUMERIC NULL,
                spread NUMERIC NULL,
                liquidity_score NUMERIC NULL,
                snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def insert_market(
    market_id: str,
    *,
    condition_id: str | None = "cond-1",
    slug: str | None = "slug-1",
    yes_token_id: str | None = "yes-1",
    no_token_id: str | None = "no-1",
    active: bool = True,
    closed: bool = False,
    archived: bool = False,
    last_seen_at: datetime | None = None,
    with_snapshot: bool = True,
) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, category, market_family,
                yes_token_id, no_token_id, outcome_tokens_json, active, closed, archived,
                accepting_orders, last_seen_at, close_time, raw_market_json, updated_at
            )
            VALUES (%s,%s,%s,%s,'politics','election',%s,%s,%s,%s,%s,%s,true,%s,now() + interval '3 days',%s,%s)
            ON CONFLICT (market_id) DO UPDATE SET
                condition_id=EXCLUDED.condition_id,
                question=EXCLUDED.question,
                slug=EXCLUDED.slug,
                yes_token_id=EXCLUDED.yes_token_id,
                no_token_id=EXCLUDED.no_token_id,
                outcome_tokens_json=EXCLUDED.outcome_tokens_json,
                active=EXCLUDED.active,
                closed=EXCLUDED.closed,
                archived=EXCLUDED.archived,
                last_seen_at=EXCLUDED.last_seen_at,
                raw_market_json=EXCLUDED.raw_market_json,
                updated_at=EXCLUDED.updated_at
            """,
            (
                market_id,
                condition_id,
                f"Will {market_id} resolve yes?",
                slug,
                yes_token_id,
                no_token_id,
                Jsonb({"yes": yes_token_id, "no": no_token_id}),
                active,
                closed,
                archived,
                last_seen_at or datetime.now(UTC),
                Jsonb({"tags": ["politics"], "volumeNum": "1200", "liquidityNum": "800"}),
                last_seen_at or datetime.now(UTC),
            ),
        )
        if with_snapshot:
            conn.execute("INSERT INTO market_snapshots_v2 (market_id, volume_24h, liquidity, spread, snapshot_at) VALUES (%s, 1200, 800, 0.02, now())", (market_id,))
        if yes_token_id and with_snapshot:
            conn.execute("INSERT INTO orderbook_snapshots (market_id, token_id, side, best_bid, best_ask, spread, liquidity_score, collected_at) VALUES (%s,%s,'YES',0.51,0.53,0.02,0.8,now())", (market_id, yes_token_id))
        if no_token_id and with_snapshot:
            conn.execute("INSERT INTO orderbook_snapshots (market_id, token_id, side, best_bid, best_ask, spread, liquidity_score, collected_at) VALUES (%s,%s,'NO',0.47,0.49,0.02,0.8,now())", (market_id, no_token_id))
