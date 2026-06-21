from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.paper_eligibility import PaperEligibilityCandidate, PaperEligibilityRun


class PaperEligibilityRepository:
    def list_exit_plan_inputs(self, conn: Connection, *, limit: int, include_blocked: bool) -> list[dict[str, Any]]:
        if not _table_exists(conn, "exit_plans"):
            return []
        status_clause = "" if include_blocked else "AND ep.status = 'COMPLETE'"
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    ep.exit_plan_id,
                    ep.thesis_id,
                    ep.risk_decision_ref AS risk_decision_id,
                    ep.market_id AS exit_market_id,
                    ep.side AS exit_side,
                    ep.status AS exit_status,
                    ep.paper_exit_ready,
                    ep.orderbook_snapshot_id AS exit_orderbook_snapshot_id,
                    ep.missing_exit_evidence,
                    ep.blockers AS exit_blockers,
                    rd.decision AS risk_decision,
                    rd.risk_status,
                    rd.risk_approved,
                    rd.is_runtime_generated AS risk_runtime_generated,
                    rd.is_dry_run_generated AS risk_dry_run_generated,
                    rd.market_id AS risk_market_id,
                    rd.orderbook_snapshot_id AS risk_orderbook_snapshot_id,
                    tp.status AS thesis_status,
                    tp.market_id AS thesis_market_id,
                    tp.side AS thesis_side,
                    tp.source_coordinator_decision_id AS coordinator_decision_id,
                    tp.source_brain_output_ids,
                    tp.source_signal_ids,
                    tp.orderbook_snapshot_id AS thesis_orderbook_snapshot_id,
                    tp.is_runtime_generated AS thesis_runtime_generated,
                    tp.is_dry_run_generated AS thesis_dry_run_generated,
                    cd.metadata_json AS coordinator_metadata,
                    cd.execution_allowed AS coordinator_execution_allowed,
                    obs.snapshot_status AS orderbook_snapshot_status,
                    obs.is_stale AS orderbook_is_stale,
                    obs.best_bid AS orderbook_best_bid,
                    obs.best_ask AS orderbook_best_ask,
                    obs.mid_price AS orderbook_mid_price,
                    obs.spread AS orderbook_spread,
                    obs.liquidity_score AS orderbook_liquidity_score,
                    link.link_confidence,
                    link.link_count
                FROM exit_plans ep
                LEFT JOIN risk_decisions rd
                    ON rd.risk_decision_id = ep.risk_decision_ref
                LEFT JOIN thesis_profiles tp
                    ON tp.thesis_id = ep.thesis_id
                LEFT JOIN coordinator_decisions cd
                    ON cd.coordinator_decision_id = tp.source_coordinator_decision_id
                LEFT JOIN orderbook_snapshots obs
                    ON obs.id = COALESCE(ep.orderbook_snapshot_id, rd.orderbook_snapshot_id, tp.orderbook_snapshot_id)
                LEFT JOIN LATERAL (
                    SELECT
                        MAX(COALESCE(sml.link_confidence, sml.confidence, 0)) AS link_confidence,
                        COUNT(*) AS link_count
                    FROM signal_market_links sml
                    WHERE sml.market_id = COALESCE(ep.market_id, rd.market_id, tp.market_id)
                      AND sml.signal_id IN (
                          SELECT jsonb_array_elements_text(COALESCE(tp.source_signal_ids, '[]'::jsonb))
                      )
                      AND COALESCE(sml.is_auto_linked, true) = true
                      AND COALESCE(sml.is_review_required, false) = false
                      AND sml.link_status IN ('confirmed', 'suggested')
                ) link ON true
                WHERE ep.created_from = 'exit_foundation'
                  AND ep.is_runtime_generated = true
                  AND ep.is_dry_run_generated = false
                  {status_clause}
                ORDER BY ep.updated_at DESC NULLS LAST, ep.created_at DESC, ep.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_candidate(self, conn: Connection, candidate: PaperEligibilityCandidate) -> tuple[dict[str, Any], bool]:
        existing = conn.execute("SELECT 1 FROM paper_eligibility_candidates WHERE eligibility_id = %s", (candidate.eligibility_id,)).fetchone()
        row = conn.execute(
            """
            INSERT INTO paper_eligibility_candidates (
                eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                coordinator_decision_id, brain_output_ids, signal_ids, market_id,
                side, status, eligibility_score, eligibility_blockers,
                missing_requirements, evidence, orderbook_snapshot_id,
                link_confidence, lineage_trusted, risk_approved, exit_ready,
                not_dry_run, paper_intent_allowed, execution_allowed,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES (
                %(eligibility_id)s, %(thesis_id)s, %(risk_decision_id)s,
                %(exit_plan_id)s, %(coordinator_decision_id)s,
                %(brain_output_ids)s, %(signal_ids)s, %(market_id)s,
                %(side)s, %(status)s, %(eligibility_score)s,
                %(eligibility_blockers)s, %(missing_requirements)s,
                %(evidence)s, %(orderbook_snapshot_id)s, %(link_confidence)s,
                %(lineage_trusted)s, %(risk_approved)s, %(exit_ready)s,
                %(not_dry_run)s, FALSE, FALSE, %(generated_by)s,
                %(producer_name)s, %(is_runtime_generated)s,
                %(is_dry_run_generated)s, COALESCE(%(created_at)s, now()), now()
            )
            ON CONFLICT (eligibility_id) DO UPDATE SET
                thesis_id = EXCLUDED.thesis_id,
                risk_decision_id = EXCLUDED.risk_decision_id,
                exit_plan_id = EXCLUDED.exit_plan_id,
                coordinator_decision_id = EXCLUDED.coordinator_decision_id,
                brain_output_ids = EXCLUDED.brain_output_ids,
                signal_ids = EXCLUDED.signal_ids,
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                status = EXCLUDED.status,
                eligibility_score = EXCLUDED.eligibility_score,
                eligibility_blockers = EXCLUDED.eligibility_blockers,
                missing_requirements = EXCLUDED.missing_requirements,
                evidence = EXCLUDED.evidence,
                orderbook_snapshot_id = EXCLUDED.orderbook_snapshot_id,
                link_confidence = EXCLUDED.link_confidence,
                lineage_trusted = EXCLUDED.lineage_trusted,
                risk_approved = EXCLUDED.risk_approved,
                exit_ready = EXCLUDED.exit_ready,
                not_dry_run = EXCLUDED.not_dry_run,
                paper_intent_allowed = FALSE,
                execution_allowed = FALSE,
                generated_by = EXCLUDED.generated_by,
                producer_name = EXCLUDED.producer_name,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                updated_at = now()
            RETURNING *
            """,
            _candidate_params(candidate),
        ).fetchone()
        return dict(row), existing is None

    def record_run(self, conn: Connection, run: PaperEligibilityRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO paper_eligibility_runs (
                run_id, status, exit_plans_checked, candidates_created,
                candidates_updated, eligible_count, ineligible_count,
                blocked_count, incomplete_count, missing_exit_plan_count,
                missing_risk_decision_count, missing_thesis_count,
                missing_market_count, missing_orderbook_count, missing_binding_count,
                missing_lineage_count, dry_run_blocked_count, paper_ready_before,
                paper_ready_after, orders_created, order_intents_created,
                fills_created, positions_created, live_actions_created,
                started_at, finished_at, error_summary, created_at
            )
            VALUES (
                %(run_id)s, %(status)s, %(exit_plans_checked)s,
                %(candidates_created)s, %(candidates_updated)s,
                %(eligible_count)s, %(ineligible_count)s, %(blocked_count)s,
                %(incomplete_count)s, %(missing_exit_plan_count)s,
                %(missing_risk_decision_count)s, %(missing_thesis_count)s,
                %(missing_market_count)s, %(missing_orderbook_count)s,
                %(missing_binding_count)s, %(missing_lineage_count)s,
                %(dry_run_blocked_count)s, FALSE, FALSE, 0, 0, 0, 0, 0,
                %(started_at)s, %(finished_at)s, %(error_summary)s, now()
            )
            RETURNING *
            """,
            run.model_dump(exclude={"mock_data", "candidates"}),
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "paper_eligibility_runs"):
            return None
        row = conn.execute("SELECT * FROM paper_eligibility_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def list_candidates(
        self,
        conn: Connection,
        *,
        limit: int,
        status: str | None = None,
        market_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        params.append(limit)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM paper_eligibility_candidates
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int) -> dict[str, Any]:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return _empty_summary()
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_candidates,
                COUNT(*) FILTER (WHERE status = 'ELIGIBLE') AS eligible_count,
                COUNT(*) FILTER (WHERE status = 'INELIGIBLE') AS ineligible_count,
                COUNT(*) FILTER (WHERE status = 'BLOCKED') AS blocked_count,
                COUNT(*) FILTER (WHERE status = 'INCOMPLETE') AS incomplete_count,
                COUNT(*) FILTER (WHERE paper_intent_allowed = true) AS paper_intent_allowed_count,
                COUNT(*) FILTER (WHERE execution_allowed = true) AS execution_allowed_count
            FROM paper_eligibility_candidates
            """
        ).fetchone()
        blockers = conn.execute(
            """
            SELECT item AS blocker, COUNT(*) AS count
            FROM paper_eligibility_candidates,
                 jsonb_array_elements_text(eligibility_blockers) AS item
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        missing = conn.execute(
            """
            SELECT item AS missing_requirement, COUNT(*) AS count
            FROM paper_eligibility_candidates,
                 jsonb_array_elements_text(missing_requirements) AS item
            GROUP BY item
            ORDER BY count DESC, item ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return {
            **dict(totals),
            "top_eligibility_blockers": [dict(row) for row in blockers],
            "missing_requirement_summary": [dict(row) for row in missing],
            "latest_run": self.latest_run(conn),
            "latest_candidates": self.list_candidates(conn, limit=limit),
        }


def paper_eligibility_from_row(row: dict[str, Any]) -> PaperEligibilityCandidate:
    return PaperEligibilityCandidate(
        eligibility_id=str(row["eligibility_id"]),
        thesis_id=row.get("thesis_id"),
        risk_decision_id=row.get("risk_decision_id"),
        exit_plan_id=row.get("exit_plan_id"),
        coordinator_decision_id=row.get("coordinator_decision_id"),
        brain_output_ids=_list(row.get("brain_output_ids")),
        signal_ids=_list(row.get("signal_ids")),
        market_id=row.get("market_id"),
        side=row.get("side"),
        status=row.get("status") or "ERROR",
        eligibility_score=float(row.get("eligibility_score") or 0.0),
        eligibility_blockers=_list(row.get("eligibility_blockers")),
        missing_requirements=_list(row.get("missing_requirements")),
        evidence=row.get("evidence") or {},
        orderbook_snapshot_id=int(row["orderbook_snapshot_id"]) if row.get("orderbook_snapshot_id") is not None else None,
        link_confidence=float(row["link_confidence"]) if row.get("link_confidence") is not None else None,
        lineage_trusted=bool(row.get("lineage_trusted")),
        risk_approved=bool(row.get("risk_approved")),
        exit_ready=bool(row.get("exit_ready")),
        not_dry_run=bool(row.get("not_dry_run")),
        paper_intent_allowed=bool(row.get("paper_intent_allowed")),
        execution_allowed=bool(row.get("execution_allowed")),
        generated_by=row.get("generated_by") or "runtime",
        producer_name=row.get("producer_name") or "paper_eligibility_gate",
        is_runtime_generated=bool(row.get("is_runtime_generated", True)),
        is_dry_run_generated=bool(row.get("is_dry_run_generated", False)),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _candidate_params(candidate: PaperEligibilityCandidate) -> dict[str, Any]:
    data = candidate.model_dump()
    for key in ("brain_output_ids", "signal_ids", "eligibility_blockers", "missing_requirements", "evidence"):
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
        "total_candidates": 0,
        "eligible_count": 0,
        "ineligible_count": 0,
        "blocked_count": 0,
        "incomplete_count": 0,
        "paper_intent_allowed_count": 0,
        "execution_allowed_count": 0,
        "top_eligibility_blockers": [],
        "missing_requirement_summary": [],
        "latest_run": None,
        "latest_candidates": [],
    }
