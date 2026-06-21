from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.data_foundation.contracts import MarketRulesRecord


class MarketRulesRepository:
    def upsert_rules(self, conn: Connection, record: MarketRulesRecord) -> tuple[dict[str, Any], bool]:
        existing = self.get_rules(conn, record.market_id)
        changed = existing is None or existing.get("rules_hash") != record.rules_hash
        row = conn.execute(
            """
            INSERT INTO market_rules (
                market_id, rules_text, resolution_source, resolution_source_url, settlement_method,
                resolution_source_status, resolution_source_type, resolution_source_evidence,
                resolution_source_confidence, resolution_source_penalty, resolution_source_hard_block,
                deadline_at, rules_hash, ambiguity_flags_json, raw_rules_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_id) DO UPDATE
            SET rules_text = EXCLUDED.rules_text,
                resolution_source = EXCLUDED.resolution_source,
                resolution_source_url = EXCLUDED.resolution_source_url,
                settlement_method = EXCLUDED.settlement_method,
                resolution_source_status = EXCLUDED.resolution_source_status,
                resolution_source_type = EXCLUDED.resolution_source_type,
                resolution_source_evidence = EXCLUDED.resolution_source_evidence,
                resolution_source_confidence = EXCLUDED.resolution_source_confidence,
                resolution_source_penalty = EXCLUDED.resolution_source_penalty,
                resolution_source_hard_block = EXCLUDED.resolution_source_hard_block,
                deadline_at = EXCLUDED.deadline_at,
                rules_hash = EXCLUDED.rules_hash,
                ambiguity_flags_json = EXCLUDED.ambiguity_flags_json,
                raw_rules_json = EXCLUDED.raw_rules_json,
                last_seen_at = now(),
                updated_at = now()
            RETURNING *
            """,
            (
                record.market_id,
                record.rules_text,
                record.resolution_source,
                record.resolution_source_url,
                record.settlement_method,
                record.resolution_source_status,
                record.resolution_source_type,
                record.resolution_source_evidence,
                record.resolution_source_confidence,
                record.resolution_source_penalty,
                record.resolution_source_hard_block,
                record.deadline_at,
                record.rules_hash,
                Jsonb(record.ambiguity_flags_json),
                Jsonb(record.raw_rules_json),
            ),
        ).fetchone()
        return row, changed

    def get_rules(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM market_rules WHERE market_id = %s", (market_id,)).fetchone()

    def coverage_stats(self, conn: Connection) -> dict[str, Any]:
        return conn.execute(
            """
            SELECT
                COUNT(*) AS markets_with_rules,
                COUNT(*) FILTER (WHERE rules_text IS NULL OR rules_text = '') AS markets_missing_rules
            FROM market_rules
            """
        ).fetchone()
