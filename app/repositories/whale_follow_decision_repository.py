from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.whale_neuron.contracts import WhaleFollowDecision


class WhaleFollowDecisionRepository:
    def insert_decision(self, conn: Connection, decision: WhaleFollowDecision) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO whale_follow_decisions (
                whale_follow_decision_id, whale_id, market_id, whale_event_id, decision,
                follow_value, noise_score, confidence, reason, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (decision.whale_follow_decision_id, decision.whale_id, decision.market_id, decision.whale_event_id, decision.decision.value, decision.follow_value, decision.noise_score, decision.confidence, decision.reason, Jsonb({})),
        ).fetchone()

    def list_for_whale(self, conn: Connection, whale_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM whale_follow_decisions WHERE whale_id = %s ORDER BY created_at DESC LIMIT %s", (whale_id, limit)).fetchall()

    def list_for_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM whale_follow_decisions WHERE market_id = %s ORDER BY created_at DESC LIMIT %s", (market_id, limit)).fetchall()
