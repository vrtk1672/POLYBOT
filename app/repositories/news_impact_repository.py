from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.news_neuron.contracts import NewsImpactScore


class NewsImpactRepository:
    def insert_impact(self, conn: Connection, impact: NewsImpactScore) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO news_impact_scores (
                impact_id, news_event_id, market_id, direction, strength,
                confidence, urgency, already_priced_in, ttl_seconds,
                source_reliability, reason, risk_flags_json, signal_json,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (impact_id) DO UPDATE
            SET metadata_json = news_impact_scores.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            (
                impact.impact_id,
                impact.news_event_id,
                impact.market_id,
                impact.direction.value,
                impact.strength,
                impact.confidence,
                impact.urgency,
                impact.already_priced_in,
                impact.ttl_seconds,
                impact.source_reliability,
                impact.reason,
                Jsonb(impact.risk_flags),
                Jsonb(impact.signal),
                Jsonb({}),
            ),
        ).fetchone()

    def list_top(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        min_strength: float | None = None,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if min_strength is not None:
            clauses.append("strength >= %s")
            params.append(min_strength)
        if min_confidence is not None:
            clauses.append("confidence >= %s")
            params.append(min_confidence)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(
            f"SELECT * FROM news_impact_scores {where} ORDER BY strength DESC, confidence DESC, created_at DESC LIMIT %s",
            params,
        ).fetchall()

    def list_by_market(self, conn: Connection, market_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT * FROM news_impact_scores
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

