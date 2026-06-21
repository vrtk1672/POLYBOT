from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.logging import get_logger
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.exit_foundation import ExitFoundationService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.risk_core import RiskCoreService
from app.services.system_power import SystemPowerService

logger = get_logger(__name__)

TRUSTED_LINK_CONFIDENCE = 0.8
FRESH_ORDERBOOK_SECONDS = 180
STALE_THESIS_REQUIREMENTS = {
    "MISSING_MARKET_LINK",
    "MISSING_SIGNAL_MARKET_BINDING",
    "MISSING_FRESH_ORDERBOOK",
    "ORDERBOOK_SNAPSHOTS_MISSING",
    "MISSING_SIDE",
    "NO_RISK_CORE",
    "NO_EXIT_FOUNDATION",
}


class PostSideRiskExitReadinessService:
    """Recover Risk/Exit readiness after deterministic side evidence exists.

    The service does not approve risk or mark exits ready directly. It only refreshes
    thesis profile evidence when current side/binding/orderbook truth proves old
    coordinator-era missing requirements are stale, then reruns the existing gates.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        system_power: SystemPowerService | None = None,
        governor: StateGovernor | None = None,
        risk_service: RiskCoreService | None = None,
        exit_service: ExitFoundationService | None = None,
        eligibility_service: PaperEligibilityService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._risk = risk_service or RiskCoreService(connection_factory=self._factory)
        self._exit = exit_service or ExitFoundationService(connection_factory=self._factory)
        self._eligibility = eligibility_service or PaperEligibilityService(connection_factory=self._factory)

    def run_recovery(self, *, cycle_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"post_side_risk_exit_{uuid4().hex}"
        power = self._system_power.get_power_state()
        system_power = str(power.get("power") or "OFF").upper()
        if system_power != "ON" or not bool(power.get("runtime_work_allowed")):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "SYSTEM_POWER_OFF")
            self._record_run(payload)
            return _json_safe(payload)
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            payload = self._blocked_payload(run_id, cycle_id, system_power, started_at, "STATE_GOVERNOR_BLOCKED_INTELLIGENCE")
            self._record_run(payload)
            return _json_safe(payload)
        existing = self._existing_for_cycle(cycle_id)
        if existing:
            existing["mock_data"] = False
            existing["idempotent"] = True
            return _json_safe(existing)

        before = self._readiness_counts()
        safety_before = self._safety_counts()
        trace_before = self.candidate_trace(limit=10)
        errors: list[str] = []
        thesis_result: dict[str, Any] = {}
        risk: dict[str, Any] = {}
        exit_result: dict[str, Any] = {}
        eligibility: dict[str, Any] = {}

        try:
            thesis_result = self._recover_thesis_readiness(limit=limit)
        except Exception as exc:
            errors.append(f"thesis_readiness:{type(exc).__name__}:{exc}")
            logger.exception("post_side_thesis_readiness_failed cycle_id=%s", cycle_id)

        try:
            risk = self._risk.evaluate_risk(limit=limit, include_blocked=True, write_decisions=True)
        except Exception as exc:
            errors.append(f"risk:{type(exc).__name__}:{exc}")
            logger.exception("post_side_risk_recompute_failed cycle_id=%s", cycle_id)

        try:
            exit_result = self._exit.build_exit_plans(limit=limit, include_blocked=True, write_plans=True)
        except Exception as exc:
            errors.append(f"exit:{type(exc).__name__}:{exc}")
            logger.exception("post_side_exit_recompute_failed cycle_id=%s", cycle_id)

        try:
            eligibility = self._eligibility.evaluate_candidates(limit=limit, include_blocked=True, write_candidates=True)
        except Exception as exc:
            errors.append(f"eligibility:{type(exc).__name__}:{exc}")
            logger.exception("post_side_eligibility_recompute_failed cycle_id=%s", cycle_id)

        after = self._readiness_counts()
        safety_after = self._safety_counts()
        trace_after = self.candidate_trace(limit=10)
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "DEGRADED" if errors else "OK",
            "candidates_checked": _int(thesis_result.get("candidates_checked")),
            "candidates_with_side": after["candidates_with_side"],
            "thesis_recovered": _int(thesis_result.get("thesis_recovered")),
            "thesis_still_blocked": _int(thesis_result.get("thesis_still_blocked")),
            "risk_checked": _int(risk.get("thesis_profiles_checked")),
            "risk_approved_before": before["risk_approved"],
            "risk_approved_after": after["risk_approved"],
            "exit_checked": _int(exit_result.get("risk_decisions_checked")),
            "exit_ready_before": before["exit_ready"],
            "exit_ready_after": after["exit_ready"],
            "eligible_before": before["eligible"],
            "eligible_after": after["eligible"],
            "paper_intents_before": before["paper_intents"],
            "paper_intents_after": after["paper_intents"],
            "candidates_missing_orderbook": after["candidates_missing_orderbook"],
            "candidates_missing_mid_price": after["candidates_missing_mid_price"],
            "candidates_missing_thesis": after["candidates_missing_thesis"],
            "candidates_missing_context_edge": after["candidates_missing_context_edge"],
            "candidates_missing_exit_policy": after["candidates_missing_exit_policy"],
            "paper_positions_delta": max(0, safety_after["paper_positions"] - safety_before["paper_positions"]),
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["real_orders"] - safety_before["real_orders"]),
            "top_risk_blockers_json": self._top_risk_blockers(limit=10),
            "top_exit_blockers_json": self._top_exit_blockers(limit=10),
            "error_message": "; ".join(errors) if errors else None,
            "metadata": {
                "risk_status": risk.get("status"),
                "exit_status": exit_result.get("status"),
                "eligibility_status": eligibility.get("status"),
                "thesis_recovery": thesis_result,
                "trace_before": trace_before,
                "trace_after": trace_after,
                "no_intent_or_execution_called_by_this_service": True,
                "root_cause": self._root_cause(after),
            },
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        latest = self._latest_run()
        counts = self._readiness_counts()
        power = self._system_power.get_power_state()
        return {
            "mock_data": False,
            "status": "OK" if latest else "EMPTY",
            "recovery_allowed": bool(power.get("runtime_work_allowed")),
            "latest_recovery_run_at": latest.get("finished_at") if latest else None,
            "latest_recovery_status": latest.get("status") if latest else None,
            "latest_run": latest,
            "candidates_with_side": counts["candidates_with_side"],
            "candidates_checked": _int((latest or {}).get("candidates_checked")),
            "risk_approved_before": _int((latest or {}).get("risk_approved_before")),
            "risk_approved_after": counts["risk_approved"],
            "exit_ready_before": _int((latest or {}).get("exit_ready_before")),
            "exit_ready_after": counts["exit_ready"],
            "eligible_before": _int((latest or {}).get("eligible_before")),
            "eligible_after": counts["eligible"],
            "paper_intents_before": _int((latest or {}).get("paper_intents_before")),
            "paper_intents_after": counts["paper_intents"],
            "top_risk_blockers": self._top_risk_blockers(limit=limit),
            "top_exit_blockers": self._top_exit_blockers(limit=limit),
            "candidates_missing_orderbook": counts["candidates_missing_orderbook"],
            "candidates_missing_mid_price": counts["candidates_missing_mid_price"],
            "candidates_missing_thesis": counts["candidates_missing_thesis"],
            "candidates_missing_context_edge": counts["candidates_missing_context_edge"],
            "candidates_missing_exit_policy": counts["candidates_missing_exit_policy"],
            "candidate_trace": self.candidate_trace(limit=10),
            "root_cause": self._root_cause(counts),
            "live_orders": counts["live_orders"],
            "real_orders": counts["real_orders"],
            "no_live_execution": counts["live_orders"] == 0,
            "paper_ready": False,
            "last_updated": datetime.now(UTC).isoformat(),
        }

    def candidate_trace(self, *, limit: int = 10) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return []
            rows = conn.execute(
                """
                WITH selected_candidates AS (
                    SELECT *
                    FROM paper_eligibility_candidates
                    WHERE side IN ('YES', 'NO')
                    ORDER BY
                        CASE WHEN status = 'ELIGIBLE' THEN 0 ELSE 1 END,
                        updated_at DESC NULLS LAST,
                        created_at DESC,
                        id DESC
                    LIMIT %s
                )
                SELECT
                    pec.eligibility_id AS candidate_id,
                    pec.market_id,
                    pec.side,
                    sml.side_source AS matched_side_source,
                    sml.side_confidence,
                    sml.id AS signal_market_link_id,
                    nsb.id AS neuron_signal_binding_id,
                    CASE WHEN sml.id IS NOT NULL THEN 'YES' ELSE 'NO' END AS trusted_binding,
                    pec.orderbook_snapshot_id,
                    CASE WHEN obs.id IS NOT NULL THEN 'YES' ELSE 'NO' END AS orderbook_fresh,
                    obs.best_bid,
                    obs.best_ask,
                    obs.mid_price,
                    obs.spread,
                    obs.liquidity_score,
                    tp.thesis_id AS thesis_profile_id,
                    pt.thesis_id AS position_thesis_profile_id,
                    tp.status AS thesis_status,
                    rd.risk_decision_id,
                    rd.decision AS risk_status,
                    rd.blockers AS risk_blockers,
                    rd.required_missing_evidence AS risk_required_missing_evidence,
                    ep.exit_plan_id,
                    ep.status AS exit_status,
                    ep.blockers AS exit_blockers,
                    ep.missing_exit_evidence AS exit_required_missing_evidence,
                    pec.status AS eligibility_status,
                    pec.eligibility_blockers,
                    pi.paper_intent_id,
                    CASE
                        WHEN tp.thesis_id IS NULL THEN 'MISSING_THESIS'
                        WHEN tp.status <> 'COMPLETE' THEN 'THESIS_NOT_COMPLETE'
                        WHEN obs.id IS NULL THEN 'MISSING_FRESH_ORDERBOOK'
                        WHEN obs.mid_price IS NULL THEN 'MISSING_MID_PRICE'
                        WHEN sml.id IS NULL THEN 'MISSING_TRUSTED_BINDING'
                        WHEN NOT COALESCE(rd.risk_approved, false) THEN 'RISK_NOT_APPROVED'
                        WHEN NOT COALESCE(ep.paper_exit_ready, false) THEN 'EXIT_NOT_READY'
                        WHEN pec.status <> 'ELIGIBLE' THEN 'ELIGIBILITY_BLOCKED'
                        ELSE 'READY_FOR_PAPER_INTENT_GATE'
                    END AS exact_next_blocker,
                    CASE
                        WHEN tp.thesis_id IS NULL THEN 'Create runtime thesis profile from coordinator decision.'
                        WHEN tp.status <> 'COMPLETE' THEN 'Recover thesis only if current side, trusted binding, fresh orderbook, and source trace are present.'
                        WHEN obs.id IS NULL THEN 'Attach a fresh OK orderbook snapshot for the candidate market.'
                        WHEN obs.mid_price IS NULL THEN 'Require trusted bid/ask or mid price before exit readiness.'
                        WHEN sml.id IS NULL THEN 'Require confirmed trusted signal-market link for source signal.'
                        WHEN NOT COALESCE(rd.risk_approved, false) THEN 'Risk Core must approve using existing thresholds; do not force.'
                        WHEN NOT COALESCE(ep.paper_exit_ready, false) THEN 'Exit Foundation must complete after risk approval and mid price.'
                        WHEN pec.status <> 'ELIGIBLE' THEN 'Recompute Paper Eligibility from current Risk and Exit truth.'
                        ELSE 'Existing Paper Intent Gate may handle eligible candidate.'
                    END AS smallest_valid_fix
                FROM selected_candidates pec
                LEFT JOIN thesis_profiles tp ON tp.thesis_id = pec.thesis_id
                LEFT JOIN position_thesis_profiles pt ON pt.coordinator_decision_id = pec.coordinator_decision_id
                LEFT JOIN risk_decisions rd ON rd.risk_decision_id = pec.risk_decision_id
                LEFT JOIN exit_plans ep ON ep.exit_plan_id = pec.exit_plan_id
                LEFT JOIN paper_intents pi ON pi.eligibility_id = pec.eligibility_id
                LEFT JOIN orderbook_snapshots obs
                    ON obs.id = pec.orderbook_snapshot_id
                   AND obs.snapshot_status = 'OK'
                   AND COALESCE(obs.is_stale, false) = false
                   AND COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at) >= now() - interval '180 seconds'
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM signal_market_links link
                    WHERE link.market_id = pec.market_id
                      AND link.signal_id IN (
                          SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, tp.source_signal_ids, '[]'::jsonb))
                      )
                      AND link.matched_side = pec.side
                      AND link.link_status IN ('confirmed', 'suggested')
                      AND COALESCE(link.is_review_required, false) = false
                      AND COALESCE(link.link_confidence, link.confidence, 0) >= %s
                    ORDER BY COALESCE(link.link_confidence, link.confidence, 0) DESC, link.id DESC
                    LIMIT 1
                ) sml ON true
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM neuron_signal_bindings binding
                    WHERE binding.market_id = pec.market_id
                      AND binding.matched_side = pec.side
                    ORDER BY binding.id DESC
                    LIMIT 1
                ) nsb ON true
                """,
                (limit, TRUSTED_LINK_CONFIDENCE),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _recover_thesis_readiness(self, *, limit: int) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"candidates_checked": 0, "thesis_recovered": 0, "thesis_still_blocked": 0}
        recovered = 0
        still_blocked = 0
        checked = 0
        with self._factory.connect() as conn, conn.transaction():
            rows = self._load_side_candidates(conn, limit=limit)
            checked = len(rows)
            for row in rows:
                current_missing = {str(item).upper() for item in _list(row.get("missing_evidence"))}
                current_evidence = dict(row.get("evidence") or {})
                hard_missing = self._current_hard_missing(row)
                remaining_missing = (current_missing - STALE_THESIS_REQUIREMENTS) | hard_missing
                if remaining_missing:
                    status = "INCOMPLETE"
                    still_blocked += 1
                else:
                    status = "COMPLETE"
                    recovered += 1
                if str(row.get("final_state") or "").upper() == "NO_TRADE" and not remaining_missing:
                    recovery_reason = "stale_no_trade_missing_requirements_resolved_by_current_side_binding_orderbook"
                else:
                    recovery_reason = "current_side_binding_orderbook_recomputed"
                side = str(row["candidate_side"]).upper()
                orderbook_id = row.get("fresh_orderbook_id") or row.get("candidate_orderbook_snapshot_id") or row.get("thesis_orderbook_snapshot_id")
                current_evidence["post_side_risk_exit_recovery"] = {
                    "side": side,
                    "status": status,
                    "reason": recovery_reason,
                    "trusted_binding_id": row.get("signal_market_link_id"),
                    "trusted_orderbook_link_id": row.get("trusted_orderbook_link_id"),
                    "trusted_orderbook_consumed": bool(row.get("trusted_orderbook_link_id")),
                    "orderbook_snapshot_id": orderbook_id,
                    "mid_price": _float_or_none(row.get("mid_price")),
                    "spread": _float_or_none(row.get("spread")),
                    "liquidity_score": _float_or_none(row.get("liquidity_score")),
                    "remaining_missing_evidence": sorted(remaining_missing),
                    "recovered_at": datetime.now(UTC).isoformat(),
                }
                conn.execute(
                    """
                    UPDATE thesis_profiles
                    SET side = %s,
                        expected_move = %s,
                        status = %s,
                        thesis_type = CASE
                            WHEN %s = 'COMPLETE' THEN 'RUNTIME_COORDINATOR_THESIS'
                            ELSE thesis_type
                        END,
                        why_now = CASE
                            WHEN %s = 'COMPLETE'
                                THEN 'Post-side recovery found deterministic side, trusted binding, fresh orderbook, and traceable source evidence; Risk and Exit remain required.'
                            ELSE why_now
                        END,
                        evidence = %s,
                        missing_evidence = %s,
                        orderbook_snapshot_id = COALESCE(%s, orderbook_snapshot_id),
                        updated_at = now()
                    WHERE thesis_id = %s
                    """,
                    (
                        side,
                        side,
                        status,
                        status,
                        status,
                        Jsonb(current_evidence),
                        Jsonb(sorted(remaining_missing)),
                        orderbook_id,
                        row["thesis_id"],
                    ),
                )
                if _table_exists(conn, "position_thesis_profiles"):
                    conn.execute(
                        """
                        UPDATE position_thesis_profiles
                        SET side = %s,
                            metadata_json = COALESCE(metadata_json, '{}'::jsonb) || %s,
                            updated_at = now()
                        WHERE coordinator_decision_id = %s
                        """,
                        (
                            side,
                            Jsonb({"post_side_risk_exit_recovery": current_evidence["post_side_risk_exit_recovery"]}),
                            row.get("coordinator_decision_id"),
                        ),
                    )
        return {"candidates_checked": checked, "thesis_recovered": recovered, "thesis_still_blocked": still_blocked}

    def _load_side_candidates(self, conn: Any, *, limit: int) -> list[dict[str, Any]]:
        if not _table_exists(conn, "paper_eligibility_candidates"):
            return []
        rows = conn.execute(
            """
            SELECT
                pec.eligibility_id,
                pec.side AS candidate_side,
                pec.market_id AS candidate_market_id,
                pec.orderbook_snapshot_id AS candidate_orderbook_snapshot_id,
                pec.signal_ids,
                pec.brain_output_ids,
                pec.coordinator_decision_id,
                tp.thesis_id,
                tp.status AS thesis_status,
                tp.missing_evidence,
                tp.evidence,
                tp.confidence,
                tp.source_signal_ids,
                tp.source_brain_output_ids,
                tp.orderbook_snapshot_id AS thesis_orderbook_snapshot_id,
                cd.final_state,
                cd.metadata_json AS coordinator_metadata,
                sml.id AS signal_market_link_id,
                sml.side_confidence,
                tol.link_id AS trusted_orderbook_link_id,
                COALESCE(tbook.id, obs.id) AS fresh_orderbook_id,
                COALESCE(tbook.mid_price, obs.mid_price) AS mid_price,
                COALESCE(tbook.spread, obs.spread) AS spread,
                COALESCE(tbook.liquidity_score, obs.liquidity_score) AS liquidity_score
            FROM paper_eligibility_candidates pec
            JOIN thesis_profiles tp ON tp.thesis_id = pec.thesis_id
            LEFT JOIN coordinator_decisions cd ON cd.coordinator_decision_id = tp.source_coordinator_decision_id
            LEFT JOIN trusted_orderbook_evidence_links tol
              ON tol.candidate_id = pec.eligibility_id
             AND tol.trusted = true
            LEFT JOIN orderbook_snapshots tbook
              ON tbook.id = tol.orderbook_snapshot_id
             AND tbook.snapshot_status = 'OK'
             AND COALESCE(tbook.is_stale, false) = false
            JOIN LATERAL (
                SELECT link.*
                FROM signal_market_links link
                WHERE link.market_id = pec.market_id
                  AND link.signal_id IN (
                      SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, tp.source_signal_ids, '[]'::jsonb))
                  )
                  AND link.matched_side = pec.side
                  AND link.link_status IN ('confirmed', 'suggested')
                  AND COALESCE(link.is_review_required, false) = false
                  AND COALESCE(link.link_confidence, link.confidence, 0) >= %s
                ORDER BY COALESCE(link.link_confidence, link.confidence, 0) DESC, link.id DESC
                LIMIT 1
            ) sml ON true
            LEFT JOIN LATERAL (
                SELECT book.*
                FROM orderbook_snapshots book
                WHERE book.market_id = pec.market_id
                  AND book.snapshot_status = 'OK'
                  AND COALESCE(book.is_stale, false) = false
                  AND COALESCE(book.snapshot_at, book.collected_at, book.created_at) >= now() - interval '180 seconds'
                  AND book.mid_price IS NOT NULL
                ORDER BY COALESCE(book.snapshot_at, book.collected_at, book.created_at) DESC, book.id DESC
                LIMIT 1
            ) obs ON true
            WHERE pec.side IN ('YES', 'NO')
              AND pec.is_runtime_generated = true
              AND COALESCE(pec.is_dry_run_generated, false) = false
            ORDER BY pec.updated_at DESC NULLS LAST, pec.created_at DESC, pec.id DESC
            LIMIT %s
            """,
            (TRUSTED_LINK_CONFIDENCE, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _current_hard_missing(self, row: dict[str, Any]) -> set[str]:
        missing: set[str] = set()
        if not row.get("candidate_market_id"):
            missing.add("MISSING_MARKET_ID")
        if str(row.get("candidate_side") or "").upper() not in {"YES", "NO"}:
            missing.add("MISSING_SIDE")
        if not row.get("signal_market_link_id"):
            missing.add("MISSING_TRUSTED_BINDING")
        if row.get("fresh_orderbook_id") is None:
            missing.add("MISSING_FRESH_ORDERBOOK")
        if row.get("mid_price") is None:
            missing.add("MISSING_MID_PRICE")
        if not _list(row.get("source_signal_ids")) or not _list(row.get("source_brain_output_ids")):
            missing.add("MISSING_SOURCE_TRACE")
        if _float_or_none(row.get("confidence")) is not None and float(row.get("confidence")) < 0.60:
            missing.add("CONFIDENCE_TOO_LOW")
        return missing

    def _readiness_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return _zero_counts()
        with self._factory.connect() as conn:
            return {
                "candidates_total": _count_table(conn, "paper_eligibility_candidates"),
                "candidates_with_side": _count_where(conn, "paper_eligibility_candidates", "side IN ('YES','NO')"),
                "candidates_with_side_and_trusted_binding": _side_trusted_binding_count(conn),
                "candidates_with_side_and_fresh_orderbook": _side_fresh_orderbook_count(conn),
                "candidates_with_side_and_mid_price": _side_mid_price_count(conn),
                "risk_approved": _count_where(conn, "risk_decisions", "risk_approved = true"),
                "risk_blocked": _count_where(conn, "risk_decisions", "decision = 'BLOCK'"),
                "exit_ready": _count_where(conn, "exit_plans", "COALESCE(paper_exit_ready, false) = true"),
                "exit_blocked": _count_where(conn, "exit_plans", "status = 'BLOCKED'"),
                "eligible": _count_where(conn, "paper_eligibility_candidates", "status = 'ELIGIBLE'"),
                "paper_intents": _count_table(conn, "paper_intents"),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "live_orders": _count_table(conn, "live_orders"),
                "real_orders": _count_table(conn, "orders_v2"),
                "candidates_missing_orderbook": _side_missing_orderbook_count(conn),
                "candidates_missing_mid_price": _side_missing_mid_price_count(conn),
                "candidates_missing_thesis": _side_missing_thesis_count(conn),
                "candidates_missing_context_edge": 0,
                "candidates_missing_exit_policy": _json_array_count(conn, "exit_plans", "missing_exit_evidence", "MISSING_EXIT_POLICY"),
            }

    def _top_risk_blockers(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return []
            rows = conn.execute(
                """
                SELECT item AS blocker, COUNT(*) AS count
                FROM paper_eligibility_candidates pec
                JOIN risk_decisions rd ON rd.risk_decision_id = pec.risk_decision_id,
                     jsonb_array_elements_text(COALESCE(rd.blockers, '[]'::jsonb)) AS item
                WHERE pec.side IN ('YES', 'NO')
                GROUP BY item
                ORDER BY count DESC, item ASC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def _top_exit_blockers(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return []
            rows = conn.execute(
                """
                SELECT item AS blocker, COUNT(*) AS count
                FROM paper_eligibility_candidates pec
                JOIN exit_plans ep ON ep.exit_plan_id = pec.exit_plan_id,
                     jsonb_array_elements_text(COALESCE(ep.blockers, '[]'::jsonb)) AS item
                WHERE pec.side IN ('YES', 'NO')
                GROUP BY item
                ORDER BY count DESC, item ASC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def _root_cause(self, counts: dict[str, int]) -> str | None:
        if counts.get("eligible", 0) > 0:
            return None
        if counts.get("risk_approved", 0) == 0 and counts.get("candidates_with_side", 0) > 0:
            return "Side-bearing candidates still need complete thesis evidence and existing Risk Core approval; this service only clears stale thesis blockers when current side, binding, orderbook, mid price, and source trace are present."
        if counts.get("exit_ready", 0) == 0:
            return "Exit remains blocked until Risk approval and complete mid-price based target/stop evidence exist."
        return "No eligible candidates yet; remaining blockers are current DB/runtime truth."

    def _safety_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {"paper_positions": 0, "live_orders": 0, "real_orders": 0}
        with self._factory.connect() as conn:
            return {
                "paper_positions": _count_table(conn, "paper_positions"),
                "live_orders": _count_table(conn, "live_orders"),
                "real_orders": _count_table(conn, "orders_v2"),
            }

    def _existing_for_cycle(self, cycle_id: str | None) -> dict[str, Any] | None:
        if not cycle_id or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "post_side_risk_exit_recovery_runs"):
                return None
            row = conn.execute(
                "SELECT * FROM post_side_risk_exit_recovery_runs WHERE cycle_id = %s ORDER BY id DESC LIMIT 1",
                (cycle_id,),
            ).fetchone()
            return dict(row) if row else None

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "post_side_risk_exit_recovery_runs"):
                return None
            row = conn.execute("SELECT * FROM post_side_risk_exit_recovery_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "post_side_risk_exit_recovery_runs"):
                return
            conn.execute(
                """
                INSERT INTO post_side_risk_exit_recovery_runs (
                    run_id, cycle_id, system_power, started_at, finished_at, status,
                    candidates_checked, candidates_with_side, thesis_recovered,
                    thesis_still_blocked, risk_checked, risk_approved_before,
                    risk_approved_after, exit_checked, exit_ready_before,
                    exit_ready_after, eligible_before, eligible_after,
                    paper_intents_before, paper_intents_after,
                    candidates_missing_orderbook, candidates_missing_mid_price,
                    candidates_missing_thesis, candidates_missing_context_edge,
                    candidates_missing_exit_policy, paper_positions_delta,
                    live_orders_delta, real_orders_delta, top_risk_blockers_json,
                    top_exit_blockers_json, error_message, metadata_json
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(candidates_checked)s,
                    %(candidates_with_side)s, %(thesis_recovered)s,
                    %(thesis_still_blocked)s, %(risk_checked)s,
                    %(risk_approved_before)s, %(risk_approved_after)s,
                    %(exit_checked)s, %(exit_ready_before)s, %(exit_ready_after)s,
                    %(eligible_before)s, %(eligible_after)s,
                    %(paper_intents_before)s, %(paper_intents_after)s,
                    %(candidates_missing_orderbook)s,
                    %(candidates_missing_mid_price)s,
                    %(candidates_missing_thesis)s,
                    %(candidates_missing_context_edge)s,
                    %(candidates_missing_exit_policy)s,
                    %(paper_positions_delta)s, %(live_orders_delta)s,
                    %(real_orders_delta)s, %(top_risk_blockers_json)s,
                    %(top_exit_blockers_json)s, %(error_message)s,
                    %(metadata_json)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "top_risk_blockers_json": Jsonb(_json_safe(payload.get("top_risk_blockers_json") or [])),
                    "top_exit_blockers_json": Jsonb(_json_safe(payload.get("top_exit_blockers_json") or [])),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _blocked_payload(self, run_id: str, cycle_id: str | None, system_power: str, started_at: datetime, reason: str) -> dict[str, Any]:
        return {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "BLOCKED",
            "candidates_checked": 0,
            "candidates_with_side": 0,
            "thesis_recovered": 0,
            "thesis_still_blocked": 0,
            "risk_checked": 0,
            "risk_approved_before": 0,
            "risk_approved_after": 0,
            "exit_checked": 0,
            "exit_ready_before": 0,
            "exit_ready_after": 0,
            "eligible_before": 0,
            "eligible_after": 0,
            "paper_intents_before": 0,
            "paper_intents_after": 0,
            "candidates_missing_orderbook": 0,
            "candidates_missing_mid_price": 0,
            "candidates_missing_thesis": 0,
            "candidates_missing_context_edge": 0,
            "candidates_missing_exit_policy": 0,
            "paper_positions_delta": 0,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "top_risk_blockers_json": [],
            "top_exit_blockers_json": [],
            "error_message": reason,
            "metadata": {"blocked_reason": reason},
        }


def _zero_counts() -> dict[str, int]:
    return {
        "candidates_total": 0,
        "candidates_with_side": 0,
        "candidates_with_side_and_trusted_binding": 0,
        "candidates_with_side_and_fresh_orderbook": 0,
        "candidates_with_side_and_mid_price": 0,
        "risk_approved": 0,
        "risk_blocked": 0,
        "exit_ready": 0,
        "exit_blocked": 0,
        "eligible": 0,
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "live_orders": 0,
        "real_orders": 0,
        "candidates_missing_orderbook": 0,
        "candidates_missing_mid_price": 0,
        "candidates_missing_thesis": 0,
        "candidates_missing_context_edge": 0,
        "candidates_missing_exit_policy": 0,
    }


def _side_trusted_binding_count(conn: Any) -> int:
    return _int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT pec.eligibility_id) AS count
            FROM paper_eligibility_candidates pec
            WHERE pec.side IN ('YES', 'NO')
              AND EXISTS (
                  SELECT 1
                  FROM signal_market_links sml
                  WHERE sml.market_id = pec.market_id
                    AND sml.signal_id IN (
                        SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb))
                    )
                    AND sml.matched_side = pec.side
                    AND sml.link_status IN ('confirmed', 'suggested')
                    AND COALESCE(sml.is_review_required, false) = false
                    AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
              )
            """,
            (TRUSTED_LINK_CONFIDENCE,),
        ).fetchone()["count"]
    )


def _side_fresh_orderbook_count(conn: Any) -> int:
    return _int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT pec.eligibility_id) AS count
            FROM paper_eligibility_candidates pec
            JOIN orderbook_snapshots obs
              ON obs.id = pec.orderbook_snapshot_id
             AND obs.market_id = pec.market_id
             AND obs.snapshot_status = 'OK'
             AND COALESCE(obs.is_stale, false) = false
             AND COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at) >= now() - interval '180 seconds'
            WHERE pec.side IN ('YES', 'NO')
            """
        ).fetchone()["count"]
    )


def _side_mid_price_count(conn: Any) -> int:
    return _int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT pec.eligibility_id) AS count
            FROM paper_eligibility_candidates pec
            JOIN orderbook_snapshots obs
              ON obs.id = pec.orderbook_snapshot_id
             AND obs.market_id = pec.market_id
             AND obs.mid_price IS NOT NULL
            WHERE pec.side IN ('YES', 'NO')
            """
        ).fetchone()["count"]
    )


def _side_missing_orderbook_count(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_eligibility_candidates",
        """
        side IN ('YES','NO') AND NOT EXISTS (
            SELECT 1 FROM orderbook_snapshots obs
            WHERE obs.id = paper_eligibility_candidates.orderbook_snapshot_id
              AND obs.market_id = paper_eligibility_candidates.market_id
              AND obs.snapshot_status = 'OK'
              AND COALESCE(obs.is_stale, false) = false
              AND COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at) >= now() - interval '180 seconds'
        )
        """,
    )


def _side_missing_mid_price_count(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_eligibility_candidates",
        """
        side IN ('YES','NO') AND NOT EXISTS (
            SELECT 1 FROM orderbook_snapshots obs
            WHERE obs.id = paper_eligibility_candidates.orderbook_snapshot_id
              AND obs.market_id = paper_eligibility_candidates.market_id
              AND obs.mid_price IS NOT NULL
        )
        """,
    )


def _side_missing_thesis_count(conn: Any) -> int:
    return _count_where(
        conn,
        "paper_eligibility_candidates",
        "side IN ('YES','NO') AND thesis_id IS NULL",
    )


def _json_array_count(conn: Any, table: str, column: str, value: str) -> int:
    if not _table_exists(conn, table) or not _column_exists(conn, table, column):
        return 0
    return _int(
        conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE {column} @> %s::jsonb
            """,
            (Jsonb([value]),),
        ).fetchone()["count"]
    )


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, where: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ANY (current_schemas(false))
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
