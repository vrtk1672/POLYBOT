from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.risk_core import RiskCoreRun, RiskDecision


class RiskCoreRepository:
    def list_runtime_thesis_profiles(self, conn: Connection, *, limit: int, include_blocked: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "thesis_profiles"):
            return []
        status_clause = "" if include_blocked else "AND tp.status NOT IN ('BLOCKED', 'ERROR')"
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    tp.*,
                    obs.spread AS orderbook_spread,
                    obs.liquidity_score AS orderbook_liquidity_score,
                    obs.is_stale AS orderbook_is_stale,
                    obs.snapshot_status AS orderbook_snapshot_status,
                    sml.signal_id AS linked_signal_id
                FROM thesis_profiles tp
                LEFT JOIN orderbook_snapshots obs
                    ON obs.id = tp.orderbook_snapshot_id
                LEFT JOIN LATERAL (
                    SELECT signal_id
                    FROM signal_market_links
                    WHERE market_id = tp.market_id
                      AND signal_id IN (
                          SELECT jsonb_array_elements_text(tp.source_signal_ids)
                      )
                    LIMIT 1
                ) sml ON true
                WHERE tp.is_runtime_generated = true
                  AND tp.is_dry_run_generated = false
                  {status_clause}
                ORDER BY tp.updated_at DESC NULLS LAST, tp.created_at DESC, tp.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_decision(self, conn: Connection, decision: RiskDecision) -> tuple[dict[str, Any], bool]:
        existing = conn.execute("SELECT 1 FROM risk_decisions WHERE risk_decision_id = %s", (decision.risk_decision_id,)).fetchone()
        row = conn.execute(
            """
            INSERT INTO risk_decisions (
                risk_decision_id, thesis_id, market_id, decision, risk_status, risk_score,
                confidence, max_position_size, max_loss, market_risk_score,
                liquidity_risk_score, spread_risk_score, missing_data_risk_score,
                confidence_risk_score, daily_exposure_risk_score, risk_reasons,
                blockers, warnings, required_missing_evidence, source_thesis_status,
                orderbook_snapshot_id, paper_candidate_allowed, execution_allowed,
                risk_approved, exit_required, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %(risk_decision_id)s, %(thesis_id)s, %(market_id)s, %(decision)s,
                %(risk_status)s, %(risk_score)s, %(confidence)s,
                %(max_position_size)s, %(max_loss)s, %(market_risk_score)s,
                %(liquidity_risk_score)s, %(spread_risk_score)s,
                %(missing_data_risk_score)s, %(confidence_risk_score)s,
                %(daily_exposure_risk_score)s, %(risk_reasons)s, %(blockers)s,
                %(warnings)s, %(required_missing_evidence)s,
                %(source_thesis_status)s, %(orderbook_snapshot_id)s, FALSE, FALSE,
                %(risk_approved)s, TRUE, %(generated_by)s, %(producer_name)s,
                %(is_runtime_generated)s, %(is_dry_run_generated)s,
                COALESCE(%(created_at)s, now()), now()
            )
            ON CONFLICT (risk_decision_id) DO UPDATE SET
                market_id = EXCLUDED.market_id,
                decision = EXCLUDED.decision,
                risk_status = EXCLUDED.risk_status,
                risk_score = EXCLUDED.risk_score,
                confidence = EXCLUDED.confidence,
                max_position_size = EXCLUDED.max_position_size,
                max_loss = EXCLUDED.max_loss,
                market_risk_score = EXCLUDED.market_risk_score,
                liquidity_risk_score = EXCLUDED.liquidity_risk_score,
                spread_risk_score = EXCLUDED.spread_risk_score,
                missing_data_risk_score = EXCLUDED.missing_data_risk_score,
                confidence_risk_score = EXCLUDED.confidence_risk_score,
                daily_exposure_risk_score = EXCLUDED.daily_exposure_risk_score,
                risk_reasons = EXCLUDED.risk_reasons,
                blockers = EXCLUDED.blockers,
                warnings = EXCLUDED.warnings,
                required_missing_evidence = EXCLUDED.required_missing_evidence,
                source_thesis_status = EXCLUDED.source_thesis_status,
                orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                paper_candidate_allowed = FALSE,
                execution_allowed = FALSE,
                risk_approved = EXCLUDED.risk_approved,
                exit_required = TRUE,
                generated_by = EXCLUDED.generated_by,
                producer_name = EXCLUDED.producer_name,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                updated_at = now()
            RETURNING *
            """,
            _decision_params(decision),
        ).fetchone()
        return dict(row), existing is None

    def record_run(self, conn: Connection, run: RiskCoreRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO risk_gate_runs (
                run_id, market_id, market_family, side, engine, runtime_mode,
                input_sources_json, input_completeness_score, started_at, finished_at,
                status, error, thesis_profiles_checked, risk_decisions_created,
                risk_decisions_updated, approved_count, rejected_count, blocked_count,
                warning_count, max_position_size_default, max_loss_default,
                confidence_threshold, paper_ready_before, paper_ready_after,
                orders_created, order_intents_created, fills_created, positions_created,
                live_actions_created, error_summary, created_at
            )
            VALUES (
                %(run_id)s, 'RISK_CORE_BATCH', 'NEURAL_MESH', 'UNKNOWN',
                'RISK_CORE_FOUNDATION', 'DATA_ONLY', '["thesis_profiles"]'::jsonb,
                1, %(started_at)s, %(finished_at)s, %(status)s, %(error_summary)s,
                %(thesis_profiles_checked)s, %(risk_decisions_created)s,
                %(risk_decisions_updated)s, %(approved_count)s, %(rejected_count)s,
                %(blocked_count)s, %(warning_count)s, %(max_position_size_default)s,
                %(max_loss_default)s, %(confidence_threshold)s, FALSE, FALSE,
                0, 0, 0, 0, 0, %(error_summary)s, now()
            )
            RETURNING *
            """,
            run.model_dump(exclude={"mock_data", "decisions"}),
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "risk_gate_runs"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM risk_gate_runs
            WHERE engine = 'RISK_CORE_FOUNDATION'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def list_decisions(
        self,
        conn: Connection,
        *,
        limit: int,
        decision: str | None = None,
        market_id: str | None = None,
        thesis_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not _table_exists(conn, "risk_decisions"):
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if decision:
            clauses.append("decision = %s")
            params.append(decision.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if thesis_id:
            clauses.append("thesis_id = %s")
            params.append(thesis_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM risk_decisions
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int) -> dict[str, Any]:
        if not _table_exists(conn, "risk_decisions"):
            return _empty_summary()
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_risk_decisions,
                COUNT(*) FILTER (WHERE decision = 'APPROVE') AS approved_count,
                COUNT(*) FILTER (WHERE decision = 'REJECT') AS rejected_count,
                COUNT(*) FILTER (WHERE decision = 'BLOCK') AS blocked_count,
                COUNT(*) FILTER (WHERE decision = 'WARN_ONLY') AS warning_count,
                AVG(risk_score) AS avg_risk_score,
                COUNT(*) FILTER (WHERE missing_data_risk_score >= 0.8) AS missing_data_risk_count,
                COUNT(*) FILTER (WHERE spread_risk_score >= 0.8) AS spread_risk_count,
                COUNT(*) FILTER (WHERE liquidity_risk_score >= 0.8) AS liquidity_risk_count,
                COUNT(*) FILTER (WHERE confidence_risk_score > 0) AS confidence_risk_count,
                COUNT(*) FILTER (WHERE paper_candidate_allowed = true) AS paper_candidate_allowed_count,
                COUNT(*) FILTER (WHERE risk_approved = true) AS risk_approved_count,
                COUNT(*) FILTER (WHERE execution_allowed = true) AS execution_allowed_count
            FROM risk_decisions
            """
        ).fetchone()
        blockers = conn.execute(
            """
            SELECT item AS blocker, COUNT(*) AS count
            FROM risk_decisions,
                 jsonb_array_elements_text(blockers) AS item
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        latest_run = self.latest_run(conn)
        return {
            **dict(totals),
            "top_risk_blockers": [dict(row) for row in blockers],
            "latest_run": latest_run,
            "latest_risk_decisions": self.list_decisions(conn, limit=limit),
        }


def risk_decision_from_row(row: dict[str, Any]) -> RiskDecision:
    return RiskDecision(
        risk_decision_id=str(row["risk_decision_id"]),
        thesis_id=str(row["thesis_id"]),
        market_id=row.get("market_id"),
        decision=row.get("decision") or "ERROR",
        risk_status=row.get("risk_status") or "ERROR",
        risk_score=float(row.get("risk_score") or 0.0),
        confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
        max_position_size=float(row.get("max_position_size") or 0.0),
        max_loss=float(row.get("max_loss") or 0.0),
        market_risk_score=float(row.get("market_risk_score") or 0.0),
        liquidity_risk_score=float(row.get("liquidity_risk_score") or 0.0),
        spread_risk_score=float(row.get("spread_risk_score") or 0.0),
        missing_data_risk_score=float(row.get("missing_data_risk_score") or 0.0),
        confidence_risk_score=float(row.get("confidence_risk_score") or 0.0),
        daily_exposure_risk_score=float(row.get("daily_exposure_risk_score") or 0.0),
        risk_reasons=_list(row.get("risk_reasons")),
        blockers=_list(row.get("blockers")),
        warnings=_list(row.get("warnings")),
        required_missing_evidence=_list(row.get("required_missing_evidence")),
        source_thesis_status=row.get("source_thesis_status"),
        orderbook_snapshot_id=int(row["orderbook_snapshot_id"]) if row.get("orderbook_snapshot_id") is not None else None,
        paper_candidate_allowed=bool(row.get("paper_candidate_allowed")),
        execution_allowed=bool(row.get("execution_allowed")),
        risk_approved=bool(row.get("risk_approved")),
        exit_required=bool(row.get("exit_required", True)),
        generated_by=row.get("generated_by") or "runtime",
        producer_name=row.get("producer_name") or "risk_core",
        is_runtime_generated=bool(row.get("is_runtime_generated", True)),
        is_dry_run_generated=bool(row.get("is_dry_run_generated", False)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _decision_params(decision: RiskDecision) -> dict[str, Any]:
    data = decision.model_dump()
    for key in ("risk_reasons", "blockers", "warnings", "required_missing_evidence"):
        data[key] = Jsonb(data[key])
    return data


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            return [value]
    return [str(value)]


def _table_exists(conn: Connection, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _empty_summary() -> dict[str, Any]:
    return {
        "total_risk_decisions": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "blocked_count": 0,
        "warning_count": 0,
        "avg_risk_score": 0.0,
        "missing_data_risk_count": 0,
        "spread_risk_count": 0,
        "liquidity_risk_count": 0,
        "confidence_risk_count": 0,
        "paper_candidate_allowed_count": 0,
        "risk_approved_count": 0,
        "execution_allowed_count": 0,
        "top_risk_blockers": [],
        "latest_run": None,
        "latest_risk_decisions": [],
    }
