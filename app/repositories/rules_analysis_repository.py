from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.rules_neuron.contracts import RulesAnalysisResult


class RulesAnalysisRepository:
    def insert_analysis(self, conn: Connection, result: RulesAnalysisResult) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO rules_analysis (
                rules_analysis_id, market_id, rules_hash, rules_text_present,
                resolution_source_present, deadline_present, settlement_method, deadline_at,
                ambiguous_terms_json, edge_cases_json, dangerous_edge_cases_json,
                wording_risk, dispute_risk, resolution_clarity, source_verification_status,
                jurisdiction_status, compliance_status, recommendation, cannot_trade_reason, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                result.rules_analysis_id,
                result.market_id,
                result.rules_hash,
                result.rules_text_present,
                result.resolution_source_present,
                result.deadline_present,
                result.settlement_method.value if hasattr(result.settlement_method, "value") else result.settlement_method,
                result.deadline_at,
                Jsonb(result.ambiguous_terms),
                Jsonb(result.edge_cases),
                Jsonb(result.dangerous_edge_cases),
                result.wording_risk,
                result.dispute_risk,
                result.resolution_clarity,
                result.source_verification_status.value if hasattr(result.source_verification_status, "value") else result.source_verification_status,
                result.jurisdiction_status.value if hasattr(result.jurisdiction_status, "value") else result.jurisdiction_status,
                result.compliance_status.value if hasattr(result.compliance_status, "value") else result.compliance_status,
                result.recommendation.value if hasattr(result.recommendation, "value") else result.recommendation,
                result.cannot_trade_reason,
                Jsonb(result.metadata),
            ),
        ).fetchone()

    def get_latest(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM rules_analysis WHERE market_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()

    def list_recent(self, conn: Connection, *, limit: int = 100, recommendation: str | None = None, compliance_status: str | None = None, min_wording_risk: float | None = None, min_dispute_risk: float | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if recommendation:
            clauses.append("recommendation = %s")
            params.append(recommendation)
        if compliance_status:
            clauses.append("compliance_status = %s")
            params.append(compliance_status)
        if min_wording_risk is not None:
            clauses.append("wording_risk >= %s")
            params.append(min_wording_risk)
        if min_dispute_risk is not None:
            clauses.append("dispute_risk >= %s")
            params.append(min_dispute_risk)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(f"SELECT * FROM rules_analysis {where} ORDER BY created_at DESC, id DESC LIMIT %s", params).fetchall()

