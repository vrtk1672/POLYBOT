from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory


def setup_revalidation_tables() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_universe_memory (
                id BIGSERIAL PRIMARY KEY,
                market_memory_id TEXT NOT NULL UNIQUE,
                market_id TEXT,
                condition_id TEXT,
                slug TEXT,
                title TEXT,
                question TEXT,
                category TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                active BOOLEAN NOT NULL DEFAULT true,
                tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                yes_token_id TEXT,
                no_token_id TEXT,
                identity_verification_state TEXT NOT NULL DEFAULT 'VERIFIED',
                token_verification_state TEXT NOT NULL DEFAULT 'TOKENS_VERIFIED',
                freshness_state TEXT NOT NULL DEFAULT 'FRESH',
                research_priority TEXT NOT NULL DEFAULT 'HIGH',
                liquidity NUMERIC,
                volume NUMERIC,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_event_memory (
                id BIGSERIAL PRIMARY KEY,
                source_event_id TEXT NOT NULL UNIQUE,
                source_type TEXT NOT NULL DEFAULT 'NEWS',
                source_id TEXT,
                event_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
                headline TEXT,
                direction TEXT NOT NULL DEFAULT 'UNKNOWN',
                already_priced_in_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_to_market_recall (
                id BIGSERIAL PRIMARY KEY,
                recall_id TEXT NOT NULL UNIQUE,
                source_event_id TEXT NOT NULL,
                market_memory_id TEXT,
                market_id TEXT,
                condition_id TEXT,
                link_type TEXT NOT NULL,
                link_confidence NUMERIC NOT NULL DEFAULT 0,
                matched_entities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                matched_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                confidence_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                semantic_score NUMERIC NOT NULL DEFAULT 0,
                token_side_resolution_state TEXT NOT NULL DEFAULT 'TOKEN_SIDE_UNKNOWN',
                candidate_actionability_hint TEXT NOT NULL DEFAULT 'NOT_RELEVANT',
                guardrail_reason TEXT,
                direction_for_market TEXT NOT NULL DEFAULT 'UNKNOWN',
                direction_confidence NUMERIC NOT NULL DEFAULT 0,
                eligible_for_targeted_revalidation BOOLEAN NOT NULL DEFAULT false,
                reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orderbook_snapshots (
                id BIGSERIAL PRIMARY KEY,
                orderbook_snapshot_id TEXT UNIQUE,
                market_id TEXT,
                token_id TEXT,
                best_bid NUMERIC,
                best_ask NUMERIC,
                spread NUMERIC,
                liquidity_score NUMERIC,
                depth_1c NUMERIC,
                depth_2c NUMERIC,
                depth_5c NUMERIC,
                snapshot_status TEXT NOT NULL DEFAULT 'OK',
                is_stale BOOLEAN NOT NULL DEFAULT false,
                collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                snapshot_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payout_odds_evaluations (
                id BIGSERIAL PRIMARY KEY,
                evaluation_id TEXT UNIQUE,
                market_id TEXT,
                side TEXT,
                token_id TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_technical_signals (
                id BIGSERIAL PRIMARY KEY,
                market_id TEXT,
                momentum_score NUMERIC,
                trend_strength NUMERIC,
                price_change_15m NUMERIC,
                price_change_1h NUMERIC,
                ts TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS orderbook_signals (id BIGSERIAL PRIMARY KEY, market_id TEXT, ts TIMESTAMPTZ NOT NULL DEFAULT now())")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_intents (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS paper_orders (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS paper_fills (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS paper_positions (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS live_orders (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS positions (id BIGSERIAL PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS shadow_orders (id BIGSERIAL PRIMARY KEY);
            """
        )


def insert_market(market_id: str, *, token_state: str = "TOKENS_VERIFIED", identity_state: str = "VERIFIED", status: str = "ACTIVE") -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO market_universe_memory (
                market_memory_id, market_id, condition_id, slug, title, question,
                status, active, yes_token_id, no_token_id, identity_verification_state,
                token_verification_state, freshness_state, liquidity, volume, tags_json, keywords_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'FRESH',1000,1000,%s,%s)
            ON CONFLICT (market_memory_id) DO UPDATE SET
                status=EXCLUDED.status,
                token_verification_state=EXCLUDED.token_verification_state,
                identity_verification_state=EXCLUDED.identity_verification_state,
                updated_at=now()
            """,
            (
                f"memory-{market_id}",
                market_id,
                f"cond-{market_id}",
                market_id,
                f"Market {market_id}",
                f"Market {market_id}",
                status,
                status == "ACTIVE",
                f"{market_id}-yes",
                f"{market_id}-no",
                identity_state,
                token_state,
                Jsonb(["crypto"]),
                Jsonb(["crypto", "event"]),
            ),
        )


def insert_event_link(
    event_id: str,
    market_id: str,
    *,
    link_type: str = "DIRECT_LINK",
    confidence: float = 0.90,
    hint: str = "REVALIDATION_ELIGIBLE",
    token_side_state: str = "SIDE_DIRECTIONAL_YES",
    direction: str = "YES",
    event_offset: str = "5 minutes",
) -> str:
    recall_id = f"recall-{event_id}-{market_id}-{link_type}-{hint}".replace(" ", "-")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO source_event_memory (
                source_event_id, source_type, source_id, event_timestamp, headline,
                direction, already_priced_in_state
            )
            VALUES (%s,'NEWS','fixture',now() - (%s)::interval,%s,%s,'UNKNOWN')
            ON CONFLICT (source_event_id) DO UPDATE SET updated_at=now()
            """,
            (event_id, event_offset, f"Event {event_id}", direction),
        )
        conn.execute(
            """
            INSERT INTO event_to_market_recall (
                recall_id, source_event_id, market_memory_id, market_id, condition_id,
                link_type, link_confidence, token_side_resolution_state,
                candidate_actionability_hint, direction_for_market,
                eligible_for_targeted_revalidation, reason, matched_fields_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'fixture',%s)
            ON CONFLICT (recall_id) DO UPDATE SET
                link_type=EXCLUDED.link_type,
                link_confidence=EXCLUDED.link_confidence,
                token_side_resolution_state=EXCLUDED.token_side_resolution_state,
                candidate_actionability_hint=EXCLUDED.candidate_actionability_hint,
                updated_at=now()
            """,
            (
                recall_id,
                event_id,
                f"memory-{market_id}",
                market_id,
                f"cond-{market_id}",
                link_type,
                confidence,
                token_side_state,
                hint,
                direction,
                hint == "REVALIDATION_ELIGIBLE" and link_type in {"DIRECT_LINK", "LIKELY_LINK"},
                Jsonb(["fixture"]),
            ),
        )
    return recall_id


def insert_fresh_orderbook(market_id: str, *, side: str = "YES", liquidity: float = 0.8, spread: float = 0.01, stale: bool = False) -> None:
    token = f"{market_id}-yes" if side == "YES" else f"{market_id}-no"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, best_bid, best_ask,
                spread, liquidity_score, depth_1c, snapshot_status, is_stale,
                collected_at, snapshot_at
            )
            VALUES (%s,%s,%s,0.48,0.49,%s,%s,1.0,%s,%s,now(),now())
            """,
            (f"obs-{market_id}-{side}-{stale}", market_id, token, spread, liquidity, "STALE" if stale else "OK", stale),
        )


def insert_payout(market_id: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            "INSERT INTO payout_odds_evaluations (evaluation_id, market_id, side, token_id) VALUES (%s,%s,'YES',%s)",
            (f"payout-{market_id}", market_id, f"{market_id}-yes"),
        )


def insert_movement_after(market_id: str) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            "INSERT INTO market_technical_signals (market_id, momentum_score, trend_strength, ts) VALUES (%s,0.22,0.30,now())",
            (market_id,),
        )
        conn.execute("INSERT INTO orderbook_signals (market_id, ts) VALUES (%s, now())", (market_id,))


def artifact_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions", "shadow_orders")
        }
