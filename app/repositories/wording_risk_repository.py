from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.rules_neuron.contracts import WordingRiskScore


class WordingRiskRepository:
    def insert_score(self, conn: Connection, score: WordingRiskScore) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO wording_risk_scores (
                wording_risk_id, market_id, rules_analysis_id, rules_hash,
                ambiguity_score, deadline_risk, source_risk, scope_risk,
                settlement_risk, edge_case_risk, contradiction_risk,
                total_wording_risk, risk_terms_json, explanation, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                score.wording_risk_id,
                score.market_id,
                score.rules_analysis_id,
                score.rules_hash,
                score.ambiguity_score,
                score.deadline_risk,
                score.source_risk,
                score.scope_risk,
                score.settlement_risk,
                score.edge_case_risk,
                score.contradiction_risk,
                score.total_wording_risk,
                Jsonb(score.risk_terms),
                score.explanation,
                Jsonb({}),
            ),
        ).fetchone()

    def get_latest(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM wording_risk_scores WHERE market_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()

