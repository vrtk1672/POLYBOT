from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.whale_neuron.contracts import WhaleCategory


class WhaleCategoryRepository:
    def ensure_category_run(self, conn: Connection) -> str:
        run_id = str(uuid4())
        now = datetime.now(UTC)
        conn.execute("INSERT INTO whale_category_runs (id, source_type, status, categorizer_version, started_at, ended_at, input_count, success_count, failure_count) VALUES (%s, 'v2.7', 'COMPLETED', 'v2.7', %s, %s, 1, 1, 0)", (run_id, now, now))
        return run_id

    def insert_category(self, conn: Connection, category: WhaleCategory, *, profile_id: str | None = None) -> dict[str, Any]:
        category_id = str(uuid4())
        if profile_id is None:
            row = conn.execute("SELECT id FROM whale_profiles WHERE whale_id = %s OR wallet_address = %s ORDER BY created_at DESC LIMIT 1", (category.whale_id, category.whale_id)).fetchone()
            profile_id = row["id"] if row else str(uuid4())
        primary = category.category.upper() if category.category.upper() in {"SMART_WHALE","NOISY_WHALE","MOMENTUM_WHALE","COPY_WORTHY","SPORTS_SPECIALIST","POLITICS_SPECIALIST","EVENT_SNIPER","LATE_CHASER"} else "UNCLASSIFIED"
        return conn.execute(
            """
            INSERT INTO whale_categories (
                id, wallet_address, whale_profile_id, whale_category_run_id, primary_category,
                secondary_categories_json, category_confidence, specialization_context_json,
                category_reason_codes_json, category_reason_text, explanation_json, categorizer_version,
                whale_category_id, whale_id, category, score, confidence, reason, active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'v2.7', %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (category_id, category.whale_id, profile_id, self.ensure_category_run(conn), primary, Jsonb([]), category.confidence, Jsonb({}), Jsonb([]), category.reason or category.category, Jsonb({}), category_id, category.whale_id, category.category, category.score, category.confidence, category.reason, category.active),
        ).fetchone()

    def list_for_whale(self, conn: Connection, whale_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM whale_categories WHERE whale_id = %s OR wallet_address = %s ORDER BY created_at DESC LIMIT %s", (whale_id, whale_id, limit)).fetchall()
