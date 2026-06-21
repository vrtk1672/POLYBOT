from __future__ import annotations

from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.whale_registry_entry import WhaleRegistryEntryContract


class WhaleRegistryRepository:
    def upsert(self, conn: Connection, entry: WhaleRegistryEntryContract) -> None:
        conn.execute(
            """
            INSERT INTO whale_registry (
                id, wallet_address, first_seen_at, last_seen_at, total_events,
                last_market_id, last_event_direction_class, registry_status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (wallet_address) DO UPDATE
            SET first_seen_at = LEAST(whale_registry.first_seen_at, EXCLUDED.first_seen_at),
                last_seen_at = GREATEST(whale_registry.last_seen_at, EXCLUDED.last_seen_at),
                total_events = whale_registry.total_events + EXCLUDED.total_events,
                last_market_id = CASE
                    WHEN EXCLUDED.last_seen_at >= whale_registry.last_seen_at THEN EXCLUDED.last_market_id
                    ELSE whale_registry.last_market_id
                END,
                last_event_direction_class = CASE
                    WHEN EXCLUDED.last_seen_at >= whale_registry.last_seen_at THEN EXCLUDED.last_event_direction_class
                    ELSE whale_registry.last_event_direction_class
                END,
                registry_status = CASE
                    WHEN EXCLUDED.last_seen_at >= whale_registry.last_seen_at THEN EXCLUDED.registry_status
                    ELSE whale_registry.registry_status
                END,
                metadata_json = CASE
                    WHEN EXCLUDED.last_seen_at >= whale_registry.last_seen_at THEN EXCLUDED.metadata_json
                    ELSE whale_registry.metadata_json
                END,
                updated_at = now()
            """,
            (
                entry.id,
                entry.wallet_address,
                entry.first_seen_at,
                entry.last_seen_at,
                entry.total_events,
                entry.last_market_id,
                entry.last_event_direction_class,
                entry.registry_status,
                Jsonb(entry.metadata_json),
            ),
        )

    def get_by_wallet(self, conn: Connection, wallet_address: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_registry
            WHERE wallet_address = %s
            LIMIT 1
            """,
            (wallet_address,),
        ).fetchone()

    def list_active(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_registry
            WHERE registry_status IN ('ACTIVE', 'WATCHLIST')
            ORDER BY last_seen_at DESC, updated_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def upsert_v27(self, conn: Connection, *, whale_id: str, wallet_address: str | None, display_label: str | None, market_id: str | None, event_time, notional: float | None) -> tuple[dict[str, object], bool]:
        existing = conn.execute("SELECT * FROM whale_registry WHERE whale_id = %s OR wallet_address = %s LIMIT 1", (whale_id, wallet_address or whale_id)).fetchone()
        row_id = existing["id"] if existing else str(uuid4())
        row = conn.execute(
            """
            INSERT INTO whale_registry (
                id, wallet_address, first_seen_at, last_seen_at, total_events, last_market_id,
                last_event_direction_class, registry_status, metadata_json, whale_id, display_label,
                total_notional_usd, known_market_families_json, status
            )
            VALUES (%s, %s, %s, %s, 1, %s, 'UNKNOWN', 'ACTIVE', '{}'::jsonb, %s, %s, %s, '[]'::jsonb, 'ACTIVE')
            ON CONFLICT (wallet_address) DO UPDATE
            SET last_seen_at = GREATEST(whale_registry.last_seen_at, EXCLUDED.last_seen_at),
                total_events = whale_registry.total_events + 1,
                total_notional_usd = whale_registry.total_notional_usd + EXCLUDED.total_notional_usd,
                last_market_id = COALESCE(EXCLUDED.last_market_id, whale_registry.last_market_id),
                whale_id = COALESCE(whale_registry.whale_id, EXCLUDED.whale_id),
                display_label = COALESCE(EXCLUDED.display_label, whale_registry.display_label),
                status = COALESCE(whale_registry.status, 'ACTIVE'),
                updated_at = now()
            RETURNING *
            """,
            (row_id, wallet_address or whale_id, event_time, event_time, market_id, whale_id, display_label, notional or 0),
        ).fetchone()
        return row, existing is None

    def get_by_whale_id(self, conn: Connection, whale_id: str) -> dict[str, object] | None:
        return conn.execute("SELECT * FROM whale_registry WHERE whale_id = %s OR wallet_address = %s LIMIT 1", (whale_id, whale_id)).fetchone()

    def list_v27(self, conn: Connection, *, status: str | None = None, min_notional: float | None = None, limit: int = 100) -> list[dict[str, object]]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        if min_notional is not None:
            clauses.append("total_notional_usd >= %s")
            params.append(min_notional)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(f"SELECT * FROM whale_registry {where} ORDER BY total_notional_usd DESC, last_seen_at DESC LIMIT %s", params).fetchall()
