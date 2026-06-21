from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.learning.contracts import AILearning
from app.repositories.learning_repository_helpers import recent, row_dict, rows


class AILearningRepository:
    def insert(self, conn: Connection, item: AILearning) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO ai_learning (
                ai_learning_id, ai_request_id, model_name, prompt_version, market_id,
                market_family, task_type, predicted_output_json, observed_outcome_json,
                usefulness_score, accuracy_score, cost_usd, cost_efficiency_score,
                prior_model_score, new_model_score, confidence, learning_signal, explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                item.ai_learning_id, item.ai_request_id, item.model_name, item.prompt_version,
                item.market_id, item.market_family, item.task_type, Jsonb(item.predicted_output),
                Jsonb(item.observed_outcome), item.usefulness_score, item.accuracy_score,
                item.cost_usd, item.cost_efficiency_score, item.prior_model_score,
                item.new_model_score, item.confidence, item.learning_signal, item.explanation,
            ),
        ).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "ai_learning", limit)

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return rows(conn.execute("SELECT COALESCE(model_name,'UNKNOWN') AS model_name, task_type, learning_signal, COUNT(*) AS count, AVG(accuracy_score) AS avg_accuracy FROM ai_learning GROUP BY COALESCE(model_name,'UNKNOWN'), task_type, learning_signal ORDER BY count DESC").fetchall())

