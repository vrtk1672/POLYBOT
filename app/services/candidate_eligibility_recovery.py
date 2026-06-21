from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.logging import get_logger
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.exit_foundation import ExitFoundationService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.paper_execution import PaperExecutionService
from app.services.paper_intents import PaperIntentGateService
from app.services.risk_core import RiskCoreService
from app.services.system_power import SystemPowerService

logger = get_logger(__name__)

TRUSTED_LINK_CONFIDENCE = 0.8


class CandidateEligibilityRecoveryService:
    """Recover Paper eligibility inputs from already-trusted runtime evidence.

    This service does not invent side, approval, exits, intents, orders, fills, or positions.
    It only propagates deterministic side evidence from trusted links/metadata, then reruns the
    existing Risk, Exit, Eligibility, Intent, and safe Paper Execution gates.
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
        intent_service: PaperIntentGateService | None = None,
        execution_service: PaperExecutionService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._risk = risk_service or RiskCoreService(connection_factory=self._factory)
        self._exit = exit_service or ExitFoundationService(connection_factory=self._factory)
        self._eligibility = eligibility_service or PaperEligibilityService(connection_factory=self._factory)
        self._intent = intent_service or PaperIntentGateService(connection_factory=self._factory)
        self._execution = execution_service or PaperExecutionService(connection_factory=self._factory)

    def run_recovery(self, *, cycle_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"eligibility_recovery_{uuid4().hex}"
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

        safety_before = _safety_counts(self._factory)
        before = self._readiness_counts()
        blockers_before = self._blocker_counts()
        errors: list[str] = []
        sides_recovered = 0
        risk: dict[str, Any] = {}
        exit_result: dict[str, Any] = {}
        eligibility: dict[str, Any] = {}
        intents: dict[str, Any] = {}
        execution: dict[str, Any] = {}

        try:
            sides_recovered = self._recover_sides(limit=limit)
        except Exception as exc:
            errors.append(f"side_recovery:{type(exc).__name__}:{exc}")
            logger.exception("candidate_eligibility_side_recovery_failed cycle_id=%s", cycle_id)

        try:
            risk = self._risk.evaluate_risk(limit=limit, include_blocked=True, write_decisions=True)
        except Exception as exc:
            errors.append(f"risk:{type(exc).__name__}:{exc}")
            logger.exception("candidate_eligibility_risk_recompute_failed cycle_id=%s", cycle_id)

        try:
            exit_result = self._exit.build_exit_plans(limit=limit, include_blocked=True, write_plans=True)
        except Exception as exc:
            errors.append(f"exit:{type(exc).__name__}:{exc}")
            logger.exception("candidate_eligibility_exit_recompute_failed cycle_id=%s", cycle_id)

        try:
            eligibility = self._eligibility.evaluate_candidates(limit=limit, include_blocked=True, write_candidates=True)
        except Exception as exc:
            errors.append(f"eligibility:{type(exc).__name__}:{exc}")
            logger.exception("candidate_eligibility_eligibility_recompute_failed cycle_id=%s", cycle_id)

        try:
            intents = self._intent.build_intents(limit=limit, write_intents=True, write_no_trade=True)
        except Exception as exc:
            errors.append(f"paper_intents:{type(exc).__name__}:{exc}")
            logger.exception("candidate_eligibility_intent_gate_failed cycle_id=%s", cycle_id)

        try:
            execution = self._execution.run_execution(limit=limit, cycle_id=cycle_id, correlation_id=cycle_id)
        except Exception as exc:
            errors.append(f"paper_execution:{type(exc).__name__}:{exc}")
            logger.exception("candidate_eligibility_paper_execution_failed cycle_id=%s", cycle_id)

        safety_after = _safety_counts(self._factory)
        after = self._readiness_counts()
        blockers_after = self._blocker_counts()
        payload = {
            "mock_data": False,
            "run_id": run_id,
            "cycle_id": cycle_id,
            "system_power": system_power,
            "started_at": started_at,
            "finished_at": datetime.now(UTC),
            "status": "DEGRADED" if errors else "OK",
            "candidates_checked": _int(eligibility.get("exit_plans_checked")) or before["total_candidates"],
            "sides_recovered": sides_recovered,
            "risk_checked": _int(risk.get("thesis_profiles_checked")),
            "risk_updated": _int(risk.get("risk_decisions_created")) + _int(risk.get("risk_decisions_updated")),
            "risk_approved_before": before["risk_approved"],
            "risk_approved_after": after["risk_approved"],
            "risk_blocked_before": before["risk_blocked"],
            "risk_blocked_after": after["risk_blocked"],
            "exit_checked": _int(exit_result.get("risk_decisions_checked")),
            "exit_updated": _int(exit_result.get("exit_plans_created")) + _int(exit_result.get("exit_plans_updated")),
            "exit_ready_before": before["exit_ready"],
            "exit_ready_after": after["exit_ready"],
            "exit_blocked_before": before["exit_blocked"],
            "exit_blocked_after": after["exit_blocked"],
            "eligible_before": before["eligible"],
            "eligible_after": after["eligible"],
            "blocked_before": before["blocked"],
            "blocked_after": after["blocked"],
            "missing_side_before": blockers_before["missing_side"],
            "missing_side_after": blockers_after["missing_side"],
            "missing_binding_before": blockers_before["missing_signal_market_binding"],
            "missing_binding_after": blockers_after["missing_signal_market_binding"],
            "missing_orderbook_before": blockers_before["missing_fresh_orderbook"],
            "missing_orderbook_after": blockers_after["missing_fresh_orderbook"],
            "paper_intents_before": before["paper_intents"],
            "paper_intents_after": after["paper_intents"],
            "paper_orders_delta": max(0, safety_after["paper_orders"] - safety_before["paper_orders"]),
            "paper_fills_delta": max(0, safety_after["paper_fills"] - safety_before["paper_fills"]),
            "paper_positions_delta": max(0, safety_after["paper_positions"] - safety_before["paper_positions"]),
            "live_orders_delta": max(0, safety_after["live_orders"] - safety_before["live_orders"]),
            "real_orders_delta": max(0, safety_after["real_orders"] - safety_before["real_orders"]),
            "top_blockers_json": self._top_blockers(limit=10),
            "error_message": "; ".join(errors) if errors else None,
            "metadata": {
                "risk_status": risk.get("status"),
                "exit_status": exit_result.get("status"),
                "eligibility_status": eligibility.get("status"),
                "paper_intent_status": intents.get("status"),
                "paper_execution_status": execution.get("status"),
                "no_valid_paper_intents_reason": self._no_valid_reason(after, blockers_after),
                "candidate_trace": self.candidate_trace(limit=10),
            },
        }
        self._record_run(payload)
        return _json_safe(payload)

    def get_dashboard_summary(self, *, limit: int = 20) -> dict[str, Any]:
        latest = self._latest_run()
        counts = self._readiness_counts()
        blockers = self._blocker_counts()
        power = self._system_power.get_power_state()
        return {
            "mock_data": False,
            "status": "OK" if latest else "EMPTY",
            "recovery_allowed": bool(power.get("runtime_work_allowed")),
            "latest_recovery_run_at": latest.get("finished_at") if latest else None,
            "latest_recovery_status": latest.get("status") if latest else None,
            "latest_run": _json_safe(latest),
            "candidates_checked": _int((latest or {}).get("candidates_checked")),
            "sides_recovered": _int((latest or {}).get("sides_recovered")),
            "candidates_with_side": counts["candidates_with_side"],
            "trusted_bindings_count": counts["trusted_bindings"],
            "fresh_orderbook_count": counts["fresh_orderbook_candidates"],
            "risk_approved_count": counts["risk_approved"],
            "exit_ready_count": counts["exit_ready"],
            "eligible_candidates": counts["eligible"],
            "blocked_candidates": counts["blocked"],
            "paper_intents": counts["paper_intents"],
            "executable_paper_intents": counts["executable_paper_intents"],
            "paper_orders": counts["paper_orders"],
            "paper_fills": counts["paper_fills"],
            "paper_positions": counts["paper_positions"],
            "top_blockers": self._top_blockers(limit=limit),
            "top_missing_evidence": self._top_missing(limit=limit),
            "no_valid_paper_intents_reason": self._no_valid_reason(counts, blockers),
            "candidate_trace": self.candidate_trace(limit=10),
            "real_orders": counts["real_orders"],
            "live_orders": counts["live_orders"],
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
                SELECT
                    pec.eligibility_id AS candidate_id,
                    pec.market_id,
                    pec.side,
                    COALESCE(pec.signal_ids->>0, tp.source_signal_ids->>0) AS source_signal_id,
                    COALESCE(pec.brain_output_ids->>0, tp.source_brain_output_ids->>0) AS brain_output_id,
                    pec.coordinator_decision_id,
                    pt.thesis_id AS position_thesis_profile_id,
                    pec.risk_decision_id,
                    pec.exit_plan_id,
                    pec.orderbook_snapshot_id,
                    link.binding_id,
                    link.has_trusted_binding,
                    (obs.id IS NOT NULL) AS has_fresh_orderbook,
                    (pec.side IN ('YES', 'NO')) AS has_side,
                    rd.risk_status,
                    rd.blockers AS risk_blockers,
                    ep.status AS exit_status,
                    ep.blockers AS exit_blockers,
                    pec.status AS eligibility_status,
                    pec.eligibility_blockers,
                    pi.paper_intent_id,
                    pec.missing_requirements AS exact_missing_evidence,
                    CASE
                        WHEN pec.side IS NULL THEN 'signal_market_links/neuron_signal_bindings/coordinator_metadata'
                        WHEN NOT COALESCE(link.has_trusted_binding, false) THEN 'signal_market_binding_recovery'
                        WHEN obs.id IS NULL THEN 'evidence_refresh_orderbook'
                        WHEN NOT COALESCE(rd.risk_approved, false) THEN 'risk_core'
                        WHEN NOT COALESCE(ep.paper_exit_ready, false) THEN 'exit_foundation'
                        ELSE 'paper_eligibility_gate'
                    END AS component_that_should_have_produced_missing_evidence,
                    CASE
                        WHEN pec.side IS NULL THEN 'Need trusted matched_side YES/NO from link evidence or explicit coordinator/brain metadata.'
                        WHEN NOT COALESCE(link.has_trusted_binding, false) THEN 'Need confirmed non-review signal-market link with confidence >= 0.8.'
                        WHEN obs.id IS NULL THEN 'Need fresh OK orderbook snapshot linked to candidate market/orderbook id.'
                        WHEN NOT COALESCE(rd.risk_approved, false) THEN 'Need Risk Core approval after complete thesis, trusted binding, and fresh orderbook.'
                        WHEN NOT COALESCE(ep.paper_exit_ready, false) THEN 'Need complete Exit Foundation plan with side, mid price, target, stop, and approved risk.'
                        ELSE 'Run Paper Intent Gate for eligible candidate.'
                    END AS smallest_valid_fix
                FROM paper_eligibility_candidates pec
                LEFT JOIN thesis_profiles tp ON tp.thesis_id = pec.thesis_id
                LEFT JOIN risk_decisions rd ON rd.risk_decision_id = pec.risk_decision_id
                LEFT JOIN exit_plans ep ON ep.exit_plan_id = pec.exit_plan_id
                LEFT JOIN paper_intents pi ON pi.eligibility_id = pec.eligibility_id
                LEFT JOIN position_thesis_profiles pt ON pt.coordinator_decision_id = pec.coordinator_decision_id
                LEFT JOIN orderbook_snapshots obs
                    ON obs.id = pec.orderbook_snapshot_id
                   AND obs.snapshot_status = 'OK'
                   AND COALESCE(obs.is_stale, false) = false
                   AND COALESCE(obs.snapshot_at, obs.collected_at, obs.created_at) >= now() - interval '180 seconds'
                LEFT JOIN LATERAL (
                    SELECT
                        sml.id AS binding_id,
                        true AS has_trusted_binding
                    FROM signal_market_links sml
                    WHERE sml.market_id = pec.market_id
                      AND sml.signal_id IN (
                          SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, tp.source_signal_ids, '[]'::jsonb))
                      )
                      AND sml.link_status IN ('confirmed', 'suggested')
                      AND COALESCE(sml.is_review_required, false) = false
                      AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
                    ORDER BY COALESCE(sml.link_confidence, sml.confidence, 0) DESC, sml.id DESC
                    LIMIT 1
                ) link ON true
                ORDER BY pec.updated_at DESC NULLS LAST, pec.created_at DESC, pec.id DESC
                LIMIT %s
                """,
                (TRUSTED_LINK_CONFIDENCE, limit),
            ).fetchall()
            return [_json_safe(dict(row)) for row in rows]

    def _recover_sides(self, *, limit: int) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "thesis_profiles"):
                return 0
            link_updates = conn.execute(
                """
                WITH side_candidates AS (
                    SELECT DISTINCT ON (tp.thesis_id)
                        tp.thesis_id,
                        UPPER(sml.link_evidence_json->>'matched_side') AS recovered_side,
                        sml.signal_id,
                        sml.id AS binding_id,
                        COALESCE(sml.link_confidence, sml.confidence, 0) AS confidence
                    FROM thesis_profiles tp
                    JOIN LATERAL jsonb_array_elements_text(COALESCE(tp.source_signal_ids, '[]'::jsonb)) sig(signal_id) ON true
                    JOIN signal_market_links sml
                        ON sml.signal_id = sig.signal_id
                       AND sml.market_id = tp.market_id
                    WHERE (tp.side IS NULL OR tp.side NOT IN ('YES', 'NO'))
                      AND UPPER(COALESCE(sml.link_evidence_json->>'matched_side', '')) IN ('YES', 'NO')
                      AND sml.link_status IN ('confirmed', 'suggested')
                      AND COALESCE(sml.is_review_required, false) = false
                      AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
                    ORDER BY tp.thesis_id, COALESCE(sml.link_confidence, sml.confidence, 0) DESC, sml.id DESC
                    LIMIT %s
                )
                UPDATE thesis_profiles tp
                SET side = side_candidates.recovered_side,
                    expected_move = side_candidates.recovered_side,
                    evidence = COALESCE(tp.evidence, '{}'::jsonb) || jsonb_build_object(
                        'side_recovery', jsonb_build_object(
                            'side', side_candidates.recovered_side,
                            'source_component', 'signal_market_links',
                            'source_signal_id', side_candidates.signal_id,
                            'binding_id', side_candidates.binding_id,
                            'confidence', side_candidates.confidence,
                            'recovered_at', now(),
                            'reason', 'trusted_matched_side_from_signal_market_link'
                        )
                    ),
                    updated_at = now()
                FROM side_candidates
                WHERE tp.thesis_id = side_candidates.thesis_id
                RETURNING tp.thesis_id
                """,
                (TRUSTED_LINK_CONFIDENCE, limit),
            ).fetchall()
            metadata_updates = conn.execute(
                """
                WITH side_candidates AS (
                    SELECT DISTINCT ON (tp.thesis_id)
                        tp.thesis_id,
                        UPPER(COALESCE(cd.metadata_json->>'side', cd.metadata_json->>'expected_move')) AS recovered_side,
                        cd.coordinator_decision_id,
                        cd.confidence
                    FROM thesis_profiles tp
                    JOIN coordinator_decisions cd
                        ON cd.coordinator_decision_id = tp.source_coordinator_decision_id
                    WHERE (tp.side IS NULL OR tp.side NOT IN ('YES', 'NO'))
                      AND UPPER(COALESCE(cd.metadata_json->>'side', cd.metadata_json->>'expected_move', '')) IN ('YES', 'NO')
                      AND cd.execution_allowed = false
                      AND COALESCE(cd.metadata_json->>'is_runtime_generated', 'false') = 'true'
                      AND COALESCE(cd.metadata_json->>'is_dry_run_generated', 'false') = 'false'
                    ORDER BY tp.thesis_id, cd.confidence DESC, cd.id DESC
                    LIMIT %s
                )
                UPDATE thesis_profiles tp
                SET side = side_candidates.recovered_side,
                    expected_move = side_candidates.recovered_side,
                    evidence = COALESCE(tp.evidence, '{}'::jsonb) || jsonb_build_object(
                        'side_recovery', jsonb_build_object(
                            'side', side_candidates.recovered_side,
                            'source_component', 'coordinator_decisions',
                            'source_id', side_candidates.coordinator_decision_id,
                            'confidence', side_candidates.confidence,
                            'recovered_at', now(),
                            'reason', 'explicit_side_from_runtime_coordinator_metadata'
                        )
                    ),
                    updated_at = now()
                FROM side_candidates
                WHERE tp.thesis_id = side_candidates.thesis_id
                RETURNING tp.thesis_id
                """,
                (limit,),
            ).fetchall()
            if _table_exists(conn, "position_thesis_profiles"):
                conn.execute(
                    """
                    UPDATE position_thesis_profiles pt
                    SET side = tp.side,
                        metadata_json = COALESCE(pt.metadata_json, '{}'::jsonb) || jsonb_build_object(
                            'side_recovery', jsonb_build_object(
                                'side', tp.side,
                                'source_component', 'thesis_profiles',
                                'source_id', tp.thesis_id,
                                'recovered_at', now()
                            )
                        ),
                        updated_at = now()
                    FROM thesis_profiles tp
                    WHERE pt.coordinator_decision_id = tp.source_coordinator_decision_id
                      AND tp.side IN ('YES', 'NO')
                      AND (pt.side IS NULL OR pt.side NOT IN ('YES', 'NO'))
                    """
                )
            return len(link_updates) + len(metadata_updates)

    def _readiness_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return _zero_counts()
        with self._factory.connect() as conn:
            return {
                "total_candidates": _count_table(conn, "paper_eligibility_candidates"),
                "eligible": _count_where(conn, "paper_eligibility_candidates", "status = 'ELIGIBLE'"),
                "blocked": _count_where(conn, "paper_eligibility_candidates", "status = 'BLOCKED'"),
                "candidates_with_side": _count_where(conn, "paper_eligibility_candidates", "side IN ('YES', 'NO')"),
                "trusted_bindings": _trusted_binding_count(conn),
                "fresh_orderbook_candidates": _fresh_orderbook_candidate_count(conn),
                "risk_approved": _count_where(conn, "risk_decisions", "risk_approved = true"),
                "risk_blocked": _count_where(conn, "risk_decisions", "decision = 'BLOCK'"),
                "exit_ready": _count_where(conn, "exit_plans", "paper_exit_ready = true"),
                "exit_blocked": _count_where(conn, "exit_plans", "status = 'BLOCKED'"),
                "paper_intents": _count_table(conn, "paper_intents"),
                "executable_paper_intents": _executable_intent_count(conn),
                "paper_orders": _count_table(conn, "paper_orders"),
                "paper_fills": _count_table(conn, "paper_fills"),
                "paper_positions": _count_table(conn, "paper_positions"),
                "real_orders": _count_table(conn, "orders_v2"),
                "live_orders": _count_table(conn, "live_orders"),
            }

    def _blocker_counts(self) -> dict[str, int]:
        if not self._factory.enabled:
            return {
                "missing_side": 0,
                "missing_signal_market_binding": 0,
                "missing_fresh_orderbook": 0,
                "risk_not_approved": 0,
                "exit_not_ready": 0,
                "thesis_blocked": 0,
            }
        with self._factory.connect() as conn:
            return {
                "missing_side": _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "MISSING_SIDE"),
                "missing_signal_market_binding": _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "MISSING_SIGNAL_MARKET_BINDING"),
                "missing_fresh_orderbook": _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "MISSING_FRESH_ORDERBOOK"),
                "risk_not_approved": _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "RISK_NOT_APPROVED"),
                "exit_not_ready": _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "EXIT_NOT_READY"),
                "thesis_blocked": _json_array_count(conn, "paper_eligibility_candidates", "eligibility_blockers", "THESIS_NOT_COMPLETE")
                + _json_array_count(conn, "risk_decisions", "blockers", "THESIS_BLOCKED"),
            }

    def _top_blockers(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return _top_json_items(conn, "paper_eligibility_candidates", "eligibility_blockers", "blocker", limit)

    def _top_missing(self, *, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return _top_json_items(conn, "paper_eligibility_candidates", "missing_requirements", "missing", limit)

    def _record_run(self, payload: dict[str, Any]) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            if not _table_exists(conn, "candidate_eligibility_recovery_runs"):
                return
            conn.execute(
                """
                INSERT INTO candidate_eligibility_recovery_runs (
                    run_id, cycle_id, system_power, started_at, finished_at, status,
                    candidates_checked, sides_recovered, risk_checked, risk_updated,
                    risk_approved_before, risk_approved_after, risk_blocked_before,
                    risk_blocked_after, exit_checked, exit_updated, exit_ready_before,
                    exit_ready_after, exit_blocked_before, exit_blocked_after,
                    eligible_before, eligible_after, blocked_before, blocked_after,
                    missing_side_before, missing_side_after, missing_binding_before,
                    missing_binding_after, missing_orderbook_before, missing_orderbook_after,
                    paper_intents_before, paper_intents_after, paper_orders_delta,
                    paper_fills_delta, paper_positions_delta, live_orders_delta,
                    real_orders_delta, top_blockers_json, error_message, metadata_json
                )
                VALUES (
                    %(run_id)s, %(cycle_id)s, %(system_power)s, %(started_at)s,
                    %(finished_at)s, %(status)s, %(candidates_checked)s,
                    %(sides_recovered)s, %(risk_checked)s, %(risk_updated)s,
                    %(risk_approved_before)s, %(risk_approved_after)s,
                    %(risk_blocked_before)s, %(risk_blocked_after)s,
                    %(exit_checked)s, %(exit_updated)s, %(exit_ready_before)s,
                    %(exit_ready_after)s, %(exit_blocked_before)s,
                    %(exit_blocked_after)s, %(eligible_before)s, %(eligible_after)s,
                    %(blocked_before)s, %(blocked_after)s, %(missing_side_before)s,
                    %(missing_side_after)s, %(missing_binding_before)s,
                    %(missing_binding_after)s, %(missing_orderbook_before)s,
                    %(missing_orderbook_after)s, %(paper_intents_before)s,
                    %(paper_intents_after)s, %(paper_orders_delta)s,
                    %(paper_fills_delta)s, %(paper_positions_delta)s,
                    %(live_orders_delta)s, %(real_orders_delta)s,
                    %(top_blockers_json)s, %(error_message)s, %(metadata_json)s
                )
                ON CONFLICT (run_id) DO NOTHING
                """,
                {
                    **payload,
                    "top_blockers_json": Jsonb(_json_safe(payload.get("top_blockers_json") or [])),
                    "metadata_json": Jsonb(_json_safe(payload.get("metadata") or {})),
                },
            )

    def _existing_for_cycle(self, cycle_id: str | None) -> dict[str, Any] | None:
        if not cycle_id or not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "candidate_eligibility_recovery_runs"):
                return None
            row = conn.execute(
                "SELECT * FROM candidate_eligibility_recovery_runs WHERE cycle_id = %s ORDER BY id DESC LIMIT 1",
                (cycle_id,),
            ).fetchone()
            return dict(row) if row else None

    def _latest_run(self) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            if not _table_exists(conn, "candidate_eligibility_recovery_runs"):
                return None
            row = conn.execute("SELECT * FROM candidate_eligibility_recovery_runs ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
            return _json_safe(dict(row)) if row else None

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
            "sides_recovered": 0,
            "risk_checked": 0,
            "risk_updated": 0,
            "risk_approved_before": 0,
            "risk_approved_after": 0,
            "risk_blocked_before": 0,
            "risk_blocked_after": 0,
            "exit_checked": 0,
            "exit_updated": 0,
            "exit_ready_before": 0,
            "exit_ready_after": 0,
            "exit_blocked_before": 0,
            "exit_blocked_after": 0,
            "eligible_before": 0,
            "eligible_after": 0,
            "blocked_before": 0,
            "blocked_after": 0,
            "missing_side_before": 0,
            "missing_side_after": 0,
            "missing_binding_before": 0,
            "missing_binding_after": 0,
            "missing_orderbook_before": 0,
            "missing_orderbook_after": 0,
            "paper_intents_before": 0,
            "paper_intents_after": 0,
            "paper_orders_delta": 0,
            "paper_fills_delta": 0,
            "paper_positions_delta": 0,
            "live_orders_delta": 0,
            "real_orders_delta": 0,
            "top_blockers_json": [],
            "error_message": reason,
            "metadata": {"blocked_reason": reason},
        }

    @staticmethod
    def _no_valid_reason(counts: dict[str, int], blockers: dict[str, int]) -> str | None:
        if counts.get("eligible", 0) > 0 and counts.get("paper_intents", 0) == 0:
            return "ELIGIBLE_CANDIDATES_FAILED_INTENT_GATE"
        if counts.get("eligible", 0) > 0:
            return None
        for key, reason in (
            ("missing_side", "MISSING_SIDE"),
            ("risk_not_approved", "RISK_NOT_APPROVED"),
            ("exit_not_ready", "EXIT_NOT_READY"),
            ("missing_signal_market_binding", "MISSING_SIGNAL_MARKET_BINDING"),
            ("missing_fresh_orderbook", "MISSING_FRESH_ORDERBOOK"),
            ("thesis_blocked", "THESIS_BLOCKED"),
        ):
            if blockers.get(key, 0) > 0:
                return reason
        return "NO_ELIGIBLE_CANDIDATES"


def _safety_counts(factory: DatabaseConnectionFactory) -> dict[str, int]:
    if not factory.enabled:
        return {"paper_orders": 0, "paper_fills": 0, "paper_positions": 0, "live_orders": 0, "real_orders": 0}
    with factory.connect() as conn:
        return {
            "paper_orders": _count_table(conn, "paper_orders"),
            "paper_fills": _count_table(conn, "paper_fills"),
            "paper_positions": _count_table(conn, "paper_positions"),
            "live_orders": _count_table(conn, "live_orders"),
            "real_orders": _count_table(conn, "orders_v2"),
        }


def _zero_counts() -> dict[str, int]:
    return {
        "total_candidates": 0,
        "eligible": 0,
        "blocked": 0,
        "candidates_with_side": 0,
        "trusted_bindings": 0,
        "fresh_orderbook_candidates": 0,
        "risk_approved": 0,
        "risk_blocked": 0,
        "exit_ready": 0,
        "exit_blocked": 0,
        "paper_intents": 0,
        "executable_paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "real_orders": 0,
        "live_orders": 0,
    }


def _trusted_binding_count(conn: Any) -> int:
    if not _table_exists(conn, "paper_eligibility_candidates") or not _table_exists(conn, "signal_market_links"):
        return 0
    return _int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT pec.eligibility_id) AS count
            FROM paper_eligibility_candidates pec
            WHERE EXISTS (
                SELECT 1
                FROM signal_market_links sml
                WHERE sml.market_id = pec.market_id
                  AND sml.signal_id IN (SELECT jsonb_array_elements_text(COALESCE(pec.signal_ids, '[]'::jsonb)))
                  AND sml.link_status IN ('confirmed', 'suggested')
                  AND COALESCE(sml.is_review_required, false) = false
                  AND COALESCE(sml.link_confidence, sml.confidence, 0) >= %s
            )
            """,
            (TRUSTED_LINK_CONFIDENCE,),
        ).fetchone()["count"]
    )


def _fresh_orderbook_candidate_count(conn: Any) -> int:
    if not _table_exists(conn, "paper_eligibility_candidates") or not _table_exists(conn, "orderbook_snapshots"):
        return 0
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
            """
        ).fetchone()["count"]
    )


def _executable_intent_count(conn: Any) -> int:
    if not _table_exists(conn, "paper_intents"):
        return 0
    return _int(
        conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_intents
            WHERE intent_status = 'CREATED'
              AND intent_type = 'PAPER_ENTRY_INTENT'
              AND paper_only = true
              AND live = false
              AND execution_allowed = false
              AND order_intent_created = false
              AND COALESCE(is_dry_run_generated, false) = false
              AND market_id IS NOT NULL
              AND side IS NOT NULL
              AND intended_price IS NOT NULL
              AND orderbook_snapshot_id IS NOT NULL
              AND (
                  evidence ? 'quantity'
                  OR evidence ? 'size'
                  OR evidence ? 'intended_size'
                  OR evidence ? 'open_quantity'
                  OR evidence ? 'notional'
                  OR evidence ? 'intended_notional'
              )
            """
        ).fetchone()["count"]
    )


def _top_json_items(conn: Any, table: str, column: str, label: str, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, table):
        return []
    rows = conn.execute(
        f"""
        SELECT item AS {label}, COUNT(*) AS count
        FROM {table}, jsonb_array_elements_text({column}) AS item
        GROUP BY item
        ORDER BY count DESC, item ASC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _json_array_count(conn: Any, table: str, column: str, value: str) -> int:
    if not _table_exists(conn, table):
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


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value.__class__.__name__ == "Decimal":
        return float(value)
    return value
