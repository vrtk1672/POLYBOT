from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.learning.contracts import ModelAdjustment
from app.repositories.learning_repository_helpers import recent, row_dict, rows


class ModelAdjustmentRepository:
    def insert(self, conn: Connection, item: ModelAdjustment) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO model_adjustments (
                adjustment_id, adjustment_type, target_module, target_key, current_value,
                recommended_value, reason, evidence_json, confidence, status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                item.adjustment_id, item.adjustment_type, item.target_module,
                item.target_key, item.current_value, item.recommended_value, item.reason,
                Jsonb(item.evidence), item.confidence, item.status,
            ),
        ).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "model_adjustments", limit)

    def pending(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return rows(conn.execute("SELECT * FROM model_adjustments WHERE status IN ('RECOMMENDED','REVIEW_REQUIRED') ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall())

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return rows(conn.execute("SELECT status, target_module, COUNT(*) AS count, AVG(confidence) AS avg_confidence FROM model_adjustments GROUP BY status, target_module ORDER BY count DESC").fetchall())
