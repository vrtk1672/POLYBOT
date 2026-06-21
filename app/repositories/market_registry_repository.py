from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.data_foundation.contracts import MarketRecord


class MarketRegistryRepository:
    def upsert_market(self, conn: Connection, record: MarketRecord) -> tuple[dict[str, Any], bool]:
        existing = self.get_market(conn, record.market_id)
        row = conn.execute(
            """
            INSERT INTO markets_v2 (
                market_id, condition_id, question, slug, category, market_family,
                yes_token_id, no_token_id, outcome_tokens_json, resolution_source,
                accepting_orders, closed, archived, active, close_time, resolution_time,
                raw_market_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_id) DO UPDATE
            SET condition_id = EXCLUDED.condition_id,
                question = EXCLUDED.question,
                slug = EXCLUDED.slug,
                category = EXCLUDED.category,
                market_family = EXCLUDED.market_family,
                yes_token_id = EXCLUDED.yes_token_id,
                no_token_id = EXCLUDED.no_token_id,
                outcome_tokens_json = EXCLUDED.outcome_tokens_json,
                resolution_source = EXCLUDED.resolution_source,
                accepting_orders = EXCLUDED.accepting_orders,
                closed = EXCLUDED.closed,
                archived = EXCLUDED.archived,
                active = EXCLUDED.active,
                last_seen_at = now(),
                close_time = EXCLUDED.close_time,
                resolution_time = EXCLUDED.resolution_time,
                raw_market_json = EXCLUDED.raw_market_json,
                metadata_json = markets_v2.metadata_json || EXCLUDED.metadata_json,
                updated_at = now()
            RETURNING *
            """,
            (
                record.market_id,
                record.condition_id,
                record.question,
                record.slug,
                record.category,
                record.market_family,
                record.yes_token_id,
                record.no_token_id,
                Jsonb(record.outcome_tokens_json),
                record.resolution_source,
                record.accepting_orders,
                record.closed,
                record.archived,
                record.active,
                record.close_time,
                record.resolution_time,
                Jsonb(record.raw_market_json),
                Jsonb(record.metadata_json),
            ),
        ).fetchone()
        return row, existing is None

    def get_market(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM markets_v2 WHERE market_id = %s", (market_id,)).fetchone()

    def list_active_markets(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            "SELECT * FROM markets_v2 WHERE active = true ORDER BY last_seen_at DESC LIMIT %s",
            (limit,),
        ).fetchall()

    def list_markets(
        self,
        conn: Connection,
        *,
        active: bool | None = None,
        closed: bool | None = None,
        market_family: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if active is not None:
            clauses.append("active = %s")
            params.append(active)
        if closed is not None:
            clauses.append("closed = %s")
            params.append(closed)
        if market_family:
            clauses.append("market_family = %s")
            params.append(market_family)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(
            f"SELECT * FROM markets_v2 {where} ORDER BY last_seen_at DESC, id DESC LIMIT %s",
            params,
        ).fetchall()

    def mark_market_seen(self, conn: Connection, market_id: str) -> None:
        conn.execute("UPDATE markets_v2 SET last_seen_at = now(), updated_at = now() WHERE market_id = %s", (market_id,))

    def mark_market_closed(self, conn: Connection, market_id: str) -> None:
        conn.execute(
            """
            UPDATE markets_v2
            SET closed = true, accepting_orders = false, active = false, updated_at = now()
            WHERE market_id = %s
            """,
            (market_id,),
        )
