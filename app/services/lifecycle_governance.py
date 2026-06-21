from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.freshness_governance import FreshnessGovernanceService
from app.services.risk_evidence_mesh import RiskEvidenceMeshService
from app.services.trade_lifecycle import TradeLifecycleService
from app.services.truth_state import TruthStateService


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
RISK_EVIDENCE_TTL_SECONDS = 600

SUBJECT_TYPES = {"FRESH_SEED", "PAPER_CANDIDATE", "PAPER_INTENT", "PAPER_POSITION"}
ACTIONABILITY_CLASSES = {
    "HARD_BLOCK",
    "NO_TRADE",
    "WATCH_FOR_CONFIRMATION",
    "ACTIONABLE_SMALL_PAPER",
    "ACTIONABLE_STANDARD_PAPER",
    "COMPLETE_HIGH_CONFIDENCE",
}

CRITICAL_BLOCKERS = {
    "PRICE_MISSING",
    "EXECUTABLE_PRICE_MISSING",
    "MISSING_EXECUTABLE_PRICE",
    "TRUSTED_ORDERBOOK_MISSING",
    "MISSING_TRUSTED_ORDERBOOK",
    "MISSING_FRESH_ORDERBOOK",
    "TOKEN_MISSING",
    "MISSING_TOKEN",
    "SIDE_MISSING",
    "MISSING_SIDE",
    "MARKET_ID_MISSING",
    "MISSING_MARKET_ID",
    "CONDITION_ID_MISSING",
    "MISSING_CONDITION_ID",
    "CAPITAL_RECONCILIATION_RED",
    "CAPITAL_LOCK_MISSING",
    "SAME_MARKET_OPPOSING_SIDE_BLOCK",
    "SAME_MARKET_OPPOSING_INTENT_BLOCK",
    "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK",
    "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK",
    "SAME_MARKET_BATCH_CONFLICT_BLOCK",
    "RISK_BLOCKED",
    "RISK_BLOCKED_BAD_LIQUIDITY",
    "RISK_BLOCKED_SPREAD",
    "RISK_BLOCKED_STALE_DATA",
    "RISK_BLOCKED_NO_TRUSTED_ORDERBOOK",
    "RISK_BLOCKED_MISSING_EXECUTABLE_PRICE",
    "RISK_BLOCKED_LOW_CONFIDENCE",
    "RISK_BLOCKED_NO_EDGE",
    "RISK_BLOCKED_LINEAGE",
    "RISK_BLOCKED_UNKNOWN",
    "RISK_BLOCKED_CRITICAL_MISSING",
    "RISK_BLOCKED_STALE_CRITICAL_SOURCE",
    "RISK_BLOCKED_LINEAGE_CRITICAL",
    "RISK_BLOCKED_NO_SOURCE_BACKED_EDGE",
    "RISK_NOT_APPROVED",
    "RISK_REJECTED",
    "EXIT_BLOCKED",
    "EXIT_NOT_READY",
    "CAPITAL_BLOCKED",
    "CAPITAL_BLOCKED_RECONCILIATION",
    "CAPITAL_BLOCKED_INSUFFICIENT_BALANCE",
    "CAPITAL_BLOCKED_MAX_EXPOSURE",
    "CAPITAL_BLOCKED_MAX_OPEN_POSITIONS",
    "CAPITAL_BLOCKED_DAILY_LOSS",
    "PAPER_LINEAGE_RED",
    "OPEN_POSITION_WITHOUT_FILL",
    "BOOK_UNAVAILABLE_FOR_OPEN_POSITION",
    "STALE_MARKET",
    "TOKEN_NOT_FOUND",
    "CLOB_NO_BOOK",
    "CANDIDATE_NOT_ELIGIBLE",
    "WEAK_LINEAGE_OR_PROVENANCE",
    "DRY_RUN_EVIDENCE",
    "LIFECYCLE_PLAN_MISSING",
    "TRADE_LIFECYCLE_PLAN_MISSING",
    "STALE_PAPER_INTENT",
    "STALE_PAPER_CANDIDATE",
    "STALE_LIFECYCLE_PLAN",
    "STALE_GOVERNANCE_DECISION",
    "STALE_RISK_DECISION",
    "STALE_EXIT_PLAN",
    "STALE_CAPITAL_EVALUATION",
    "STALE_ORDERBOOK",
    "STALE_SAME_MARKET_GUARD",
    "STALE_RISK_SOURCE_REFRESH_REQUIRED",
    "REFRESH_REQUIRED_BEFORE_EXECUTION",
}

LEGACY_RISK_BLOCKERS = {
    "RISK_BLOCKED",
    "RISK_BLOCKED_BAD_LIQUIDITY",
    "RISK_BLOCKED_SPREAD",
    "RISK_BLOCKED_STALE_DATA",
    "RISK_BLOCKED_NO_TRUSTED_ORDERBOOK",
    "RISK_BLOCKED_MISSING_EXECUTABLE_PRICE",
    "RISK_BLOCKED_LOW_CONFIDENCE",
    "RISK_BLOCKED_NO_EDGE",
    "RISK_BLOCKED_LINEAGE",
    "RISK_BLOCKED_UNKNOWN",
    "RISK_BLOCKED_CRITICAL_MISSING",
    "STALE_RISK_DECISION",
}

OPTIONAL_CONTEXT = {
    "WHALE_CONTEXT_MISSING",
    "NEWS_CONTEXT_MISSING",
    "SOCIAL_CONTEXT_MISSING",
    "MEMORY_CONTEXT_MISSING",
    "FAIR_PROBABILITY_MISSING",
    "AI_CONTEXT_MISSING",
    "SOURCE_RELIABILITY_MISSING",
}

CONTEXT_DEPENDENT = {
    "TIME_TO_RESOLUTION_MISSING",
    "RULES_RISK_UNKNOWN",
    "RULES_WORDING_MISSING",
    "EXIT_PRICE_MISSING",
    "EXIT_NOW_UNAVAILABLE",
    "LIQUIDITY_DEPTH_MISSING",
    "BASIC_POSITION_DATA_MISSING",
    "POSITION_WATCHDOG_MISSING",
    "SAME_MARKET_GUARD_MISSING",
    "EXIT_HOLD_MISSING",
    "CAPITAL_EFFICIENCY_MISSING",
    "CAPITAL_BRAIN_MISSING",
    "COORDINATOR_DECISION_MISSING",
}

BLOCKED_STRATEGIES = {
    "RISK_BLOCKED": "RISK_BLOCKED",
    "EXIT_BLOCKED": "EXIT_BLOCKED",
    "CAPITAL_BLOCKED": "CAPITAL_BLOCKED",
    "SAME_MARKET_BLOCKED": "SAME_MARKET_OPPOSING_SIDE_BLOCK",
}


class LifecycleGovernanceGateService:
    """Derived governance gate for Paper intent and Paper execution paths.

    The service writes only lifecycle governance decisions and sources. It does
    not create intents, orders, fills, positions, closes, or capital rows.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._lifecycle = TradeLifecycleService(connection_factory=self._factory)
        self._freshness = FreshnessGovernanceService(connection_factory=self._factory)
        self._truth = TruthStateService(connection_factory=self._factory)
        self._risk_evidence = RiskEvidenceMeshService(connection_factory=self._factory)

    def evaluate_recent(
        self,
        *,
        limit: int = 100,
        subject_type: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        subject = str(subject_type).upper() if subject_type else None
        if subject and subject not in SUBJECT_TYPES:
            return {"mock_data": False, "status": "INVALID_SUBJECT_TYPE", "decisions_created": 0}
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "decisions_created": 0}
        with self._factory.connect() as conn, conn.transaction():
            if not _tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "decisions_created": 0}
            before = _count_table(conn, "lifecycle_governance_decisions")
            safety_before = _safety_counts(conn)
            plans = _latest_plans(conn, subject_type=subject, limit=limit)
            outcomes = [
                self.evaluate_plan_with_conn(
                    conn,
                    plan,
                    write_decision=not dry_run,
                    metadata={"source_layer": "bounded_governance_evaluation"},
                )
                for plan in plans
            ]
            after = _count_table(conn, "lifecycle_governance_decisions")
            safety_after = _safety_counts(conn)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "plans_checked": len(plans),
                "decisions_created": 0 if dry_run else max(0, after - before),
                "decisions_by_actionability": dict(Counter(item["actionability_class"] for item in outcomes)),
                "latest_outcomes": outcomes[:20],
                "safety_before": safety_before,
                "safety_after": safety_after,
                "trading_mutation": safety_before != safety_after,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            }
        )

    def evaluate_subject_with_conn(
        self,
        conn: Any,
        *,
        subject_type: str,
        subject_id: str,
        request_action: str = "OBSERVE",
        allow_build: bool = True,
        force_build: bool = False,
        write_decision: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        subject = str(subject_type).upper()
        if subject not in SUBJECT_TYPES:
            return self._missing_plan_decision(
                conn,
                subject_type=subject,
                subject_id=subject_id,
                request_action=request_action,
                blocker="INVALID_SUBJECT_TYPE",
                write_decision=write_decision,
                metadata=metadata,
            )
        plan = self._lifecycle.latest_for_subject(conn, subject_type=subject, subject_id=str(subject_id))
        if allow_build and (force_build or plan is None):
            self._lifecycle.build_subject_with_conn(conn, subject_type=subject, subject_id=str(subject_id), dry_run=False)
            plan = self._lifecycle.latest_for_subject(conn, subject_type=subject, subject_id=str(subject_id))
        if plan is None:
            return self._missing_plan_decision(
                conn,
                subject_type=subject,
                subject_id=str(subject_id),
                request_action=request_action,
                blocker="LIFECYCLE_PLAN_MISSING",
                write_decision=write_decision,
                metadata=metadata,
            )
        return self.evaluate_plan_with_conn(conn, plan, request_action=request_action, write_decision=write_decision, metadata=metadata)

    def evaluate_plan_with_conn(
        self,
        conn: Any,
        plan: dict[str, Any],
        *,
        request_action: str = "OBSERVE",
        write_decision: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not _tables_ready(conn):
            return {"status": "MISSING_TABLES", "allow_paper_intent": False, "allow_paper_execution": False}
        classified = self._classify_plan(conn, plan, request_action=request_action, metadata=metadata or {})
        decision = {
            "decision_id": _decision_id(plan, classified, request_action),
            "subject_type": plan["subject_type"],
            "subject_id": str(plan["subject_id"]),
            "lifecycle_plan_id": plan.get("plan_id"),
            "market_id": plan.get("market_id"),
            "side": plan.get("side"),
            "token_id": plan.get("token_id"),
            **classified,
        }
        if write_decision:
            _upsert_decision(conn, decision, _sources_for_decision(plan, decision))
        return _json_safe({"mock_data": False, "status": "OK", **decision})

    def authorize_paper_intent(
        self,
        conn: Any,
        *,
        candidate: dict[str, Any],
        same_market_guard: dict[str, Any] | None = None,
        write_decision: bool = True,
    ) -> dict[str, Any]:
        return self.evaluate_subject_with_conn(
            conn,
            subject_type="PAPER_CANDIDATE",
            subject_id=str(candidate.get("eligibility_id") or ""),
            request_action="PAPER_INTENT",
            write_decision=write_decision,
            metadata={
                "source_layer": "paper_intent_gate",
                "same_market_guard_decision": same_market_guard or {},
                "risk_approved": bool(candidate.get("risk_approved")),
                "exit_ready": bool(candidate.get("exit_ready")),
                "lineage_trusted": bool(candidate.get("lineage_trusted")),
                "not_dry_run": bool(candidate.get("not_dry_run")),
                "candidate_status": candidate.get("status"),
            },
        )

    def authorize_paper_execution(
        self,
        conn: Any,
        *,
        intent: dict[str, Any],
        same_market_guard: dict[str, Any] | None = None,
        write_decision: bool = True,
    ) -> dict[str, Any]:
        return self.evaluate_subject_with_conn(
            conn,
            subject_type="PAPER_INTENT",
            subject_id=str(intent.get("paper_intent_id") or ""),
            request_action="PAPER_EXECUTION",
            write_decision=write_decision,
            metadata={
                "source_layer": "paper_execution",
                "same_market_guard_decision": same_market_guard or {},
                "intent_status": intent.get("intent_status"),
                "paper_only": bool(intent.get("paper_only")),
                "live": bool(intent.get("live")),
                "execution_allowed": bool(intent.get("execution_allowed")),
                "order_intent_created": bool(intent.get("order_intent_created")),
            },
        )

    def latest_for_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "lifecycle_governance_decisions"):
            return None
        return _fetchone(
            conn,
            """
            SELECT * FROM lifecycle_governance_decisions
            WHERE subject_type=%s AND subject_id=%s
            ORDER BY created_at DESC,id DESC LIMIT 1
            """,
            (str(subject_type).upper(), str(subject_id)),
        )

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty_dashboard("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "lifecycle_governance_decisions"):
                return _empty_dashboard("MISSING_TABLES", generated_at)
            totals = _fetchone(
                conn,
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE actionability_class='HARD_BLOCK') AS hard_block_count,
                    COUNT(*) FILTER (WHERE actionability_class='NO_TRADE') AS no_trade_count,
                    COUNT(*) FILTER (WHERE actionability_class='WATCH_FOR_CONFIRMATION') AS watch_count,
                    COUNT(*) FILTER (WHERE actionability_class='ACTIONABLE_SMALL_PAPER') AS actionable_small_count,
                    COUNT(*) FILTER (WHERE actionability_class='ACTIONABLE_STANDARD_PAPER') AS actionable_standard_count,
                    COUNT(*) FILTER (WHERE actionability_class='COMPLETE_HIGH_CONFIDENCE') AS high_confidence_count,
                    COUNT(*) FILTER (WHERE allow_paper_intent) AS allow_paper_intent_count,
                    COUNT(*) FILTER (WHERE allow_paper_execution) AS allow_paper_execution_count
                FROM lifecycle_governance_decisions
                """,
            ) or {}
            by_actionability = _fetchall(conn, "SELECT actionability_class, COUNT(*) AS count FROM lifecycle_governance_decisions GROUP BY actionability_class ORDER BY actionability_class")
            latest = _fetchall(
                conn,
                """
                SELECT decision_id,subject_type,subject_id,lifecycle_plan_id,market_id,side,actionability_class,
                       allow_paper_intent,allow_paper_execution,critical_blockers_json,optional_missing_json,
                       context_dependent_missing_json,reason,created_at
                FROM lifecycle_governance_decisions
                ORDER BY created_at DESC,id DESC
                LIMIT %s
                """,
                (limit,),
            )
            critical = _top_jsonb_values(conn, "critical_blockers_json", limit=limit)
            optional = _top_jsonb_values(conn, "optional_missing_json", limit=limit)
            trace_totals = _fetchone(
                conn,
                """
                SELECT
                  COUNT(*) FILTER (WHERE metadata_json->'risk_source_trace'->>'selected_risk_source'='RISK_EVIDENCE_MESH') AS risk_evidence_used_count,
                  COUNT(*) FILTER (WHERE COALESCE((metadata_json->'risk_source_trace'->>'legacy_ignored')::boolean,false)) AS legacy_risk_ignored_count,
                  COUNT(*) FILTER (WHERE metadata_json->'risk_source_trace'->>'ignored_reason' ILIKE 'Fresh non-blocking Risk Evidence Mesh evaluation selected over stale legacy risk block%%') AS stale_legacy_risk_block_ignored_count,
                  COUNT(*) FILTER (
                    WHERE metadata_json->'risk_source_trace'->>'final_risk_interpretation'='RISK_REVIEW'
                      AND actionability_class='WATCH_FOR_CONFIRMATION'
                  ) AS risk_review_promoted_to_watch_count,
                  COUNT(*) FILTER (
                    WHERE metadata_json->'risk_source_trace'->>'final_risk_interpretation'='RISK_REVIEW'
                      AND actionability_class='HARD_BLOCK'
                  ) AS risk_review_kept_blocked_count,
                  COUNT(*) FILTER (
                    WHERE metadata_json->'risk_source_trace'->>'final_risk_interpretation'='RISK_REVIEW'
                      AND actionability_class IN ('ACTIONABLE_SMALL_PAPER','ACTIONABLE_STANDARD_PAPER','COMPLETE_HIGH_CONFIDENCE')
                  ) AS risk_review_actionable_count
                FROM lifecycle_governance_decisions
                """,
            ) or {}
            risk_source_selection = _fetchall(
                conn,
                """
                SELECT COALESCE(metadata_json->'risk_source_trace'->>'selected_risk_source','UNKNOWN') AS selected_risk_source,
                       COALESCE(metadata_json->'risk_source_trace'->>'selected_risk_source_freshness','UNKNOWN') AS selected_risk_source_freshness,
                       COUNT(*) AS count
                FROM lifecycle_governance_decisions
                GROUP BY selected_risk_source, selected_risk_source_freshness
                ORDER BY count DESC, selected_risk_source
                LIMIT %s
                """,
                (limit,),
            )
            risk_review_traces = _fetchall(
                conn,
                """
                SELECT decision_id, subject_type, subject_id, market_id, side, actionability_class,
                       critical_blockers_json, optional_missing_json,
                       metadata_json->'risk_source_trace' AS risk_source_trace,
                       created_at
                FROM lifecycle_governance_decisions
                WHERE metadata_json->'risk_source_trace'->>'selected_risk_source'='RISK_EVIDENCE_MESH'
                ORDER BY created_at DESC,id DESC
                LIMIT %s
                """,
                (limit,),
            )
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_decisions": _int(totals.get("total")),
                "decisions_by_actionability": {str(row["actionability_class"]): _int(row["count"]) for row in by_actionability},
                "allow_paper_intent_count": _int(totals.get("allow_paper_intent_count")),
                "allow_paper_execution_count": _int(totals.get("allow_paper_execution_count")),
                "hard_block_count": _int(totals.get("hard_block_count")),
                "no_trade_count": _int(totals.get("no_trade_count")),
                "watch_count": _int(totals.get("watch_count")),
                "actionable_small_paper_count": _int(totals.get("actionable_small_count")),
                "actionable_standard_paper_count": _int(totals.get("actionable_standard_count")),
                "complete_high_confidence_count": _int(totals.get("high_confidence_count")),
                "critical_blockers_top": critical,
                "optional_missing_top": optional,
                "risk_evidence_used_count": _int(trace_totals.get("risk_evidence_used_count")),
                "legacy_risk_ignored_count": _int(trace_totals.get("legacy_risk_ignored_count")),
                "stale_legacy_risk_block_ignored_count": _int(trace_totals.get("stale_legacy_risk_block_ignored_count")),
                "risk_review_promoted_to_watch_count": _int(trace_totals.get("risk_review_promoted_to_watch_count")),
                "risk_review_kept_blocked_count": _int(trace_totals.get("risk_review_kept_blocked_count")),
                "risk_review_actionable_count": _int(trace_totals.get("risk_review_actionable_count")),
                "risk_source_selection_summary": risk_source_selection,
                "latest_risk_review_traces": risk_review_traces,
                "bypass_paths_found": [],
                "latest_decisions": latest,
            }
        )

    def detail(self, decision_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "decision_id": decision_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "lifecycle_governance_decisions"):
                return {"mock_data": False, "status": "MISSING_TABLES", "decision_id": decision_id}
            decision = _fetchone(conn, "SELECT * FROM lifecycle_governance_decisions WHERE decision_id=%s", (decision_id,))
            if decision is None:
                return {"mock_data": False, "status": "NOT_FOUND", "decision_id": decision_id}
            sources = _fetchall(conn, "SELECT * FROM lifecycle_governance_sources WHERE decision_id=%s ORDER BY linked_at,id", (decision_id,))
            plan = _fetchone(conn, "SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (decision.get("lifecycle_plan_id"),)) if decision.get("lifecycle_plan_id") and _table_exists(conn, "trade_lifecycle_plans") else None
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": datetime.now(UTC).isoformat(),
                "decision": decision,
                "sources": sources,
                "lifecycle_plan": plan,
                "forensics_link": f"/dashboard/api/v2/paper/trade-forensics/{decision['subject_id']}" if decision.get("subject_type") == "PAPER_POSITION" else None,
            }
        )

    def _missing_plan_decision(
        self,
        conn: Any,
        *,
        subject_type: str,
        subject_id: str,
        request_action: str,
        blocker: str,
        write_decision: bool,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        decision = {
            "decision_id": _stable_decision_id(subject_type, subject_id, None, request_action, "HARD_BLOCK", [blocker]),
            "subject_type": subject_type,
            "subject_id": str(subject_id),
            "lifecycle_plan_id": None,
            "market_id": None,
            "side": None,
            "token_id": None,
            "actionability_class": "HARD_BLOCK",
            "allow_paper_intent": False,
            "allow_paper_execution": False,
            "critical_blockers_json": [blocker],
            "optional_missing_json": [],
            "context_dependent_missing_json": [],
            "mesh_contributions_count": 0,
            "coordinator_decision_id": None,
            "same_market_guard_status": None,
            "capital_status": None,
            "risk_status": None,
            "exit_status": None,
            "reason": f"{request_action} blocked: {blocker}",
            "metadata_json": {"request_action": request_action, **(metadata or {})},
        }
        if write_decision and _tables_ready(conn):
            _upsert_decision(conn, decision, [])
        return _json_safe({"mock_data": False, "status": "OK", **decision})

    def _classify_plan(self, conn: Any, plan: dict[str, Any], *, request_action: str, metadata: dict[str, Any]) -> dict[str, Any]:
        missing = {str(item).upper() for item in _list(plan.get("missing_inputs_json"))}
        critical = set(missing & CRITICAL_BLOCKERS)
        optional = set(missing & OPTIONAL_CONTEXT)
        context = set(missing & CONTEXT_DEPENDENT)

        strategy_type = str(plan.get("strategy_type") or "").upper()
        plan_status = str(plan.get("plan_status") or "").upper()
        decision_class = str(plan.get("decision_class") or "").upper()
        if strategy_type in BLOCKED_STRATEGIES and strategy_type != "SAME_MARKET_BLOCKED":
            critical.add(BLOCKED_STRATEGIES[strategy_type])
        if (plan_status == "BLOCKED" or decision_class == "BLOCKED") and strategy_type != "SAME_MARKET_BLOCKED":
            critical.add(_blocked_reason_from_plan(plan))

        same_market_guard = _dict(metadata.get("same_market_guard_decision")) or _dict(plan.get("same_market_summary_json"))
        same_market_status = str(same_market_guard.get("decision") or same_market_guard.get("status") or "").upper() or None
        same_market_blocker = str(same_market_guard.get("blocker_reason") or "").upper()
        same_market_truth = _same_market_truth(self._truth, conn, plan, same_market_guard)
        same_market_can_authorize = not same_market_guard or same_market_truth.get("decision_permission") == "CAN_AUTHORIZE"
        same_market_has_blocking_claim = same_market_status == "BLOCK" or bool(same_market_blocker)
        if strategy_type == "SAME_MARKET_BLOCKED" and not same_market_guard:
            critical.add("STALE_SAME_MARKET_GUARD")
            same_market_status = "REFRESH_REQUIRED"
        elif same_market_guard and not same_market_can_authorize:
            if request_action in {"PAPER_INTENT", "PAPER_EXECUTION"} or same_market_has_blocking_claim:
                critical.add("STALE_SAME_MARKET_GUARD")
                same_market_status = "REFRESH_REQUIRED"
        elif same_market_blocker in {
            "SAME_MARKET_OPPOSING_SIDE_BLOCK",
            "SAME_MARKET_OPPOSING_INTENT_BLOCK",
            "SAME_MARKET_OPEN_OPPOSITE_POSITION_BLOCK",
            "SAME_MARKET_ACTIVE_OPPOSITE_INTENT_BLOCK",
            "SAME_MARKET_BATCH_CONFLICT_BLOCK",
        }:
            critical.add(same_market_blocker)
        if same_market_status == "ALLOW" and same_market_can_authorize:
            context.discard("SAME_MARKET_GUARD_MISSING")

        risk_summary = _dict(plan.get("risk_summary_json"))
        exit_summary = _dict(plan.get("exit_hold_summary_json")) or _dict(plan.get("exit_summary_json"))
        exit_plan_readiness = _exit_plan_readiness_summary(conn, plan)
        capital_summary = _dict(plan.get("capital_efficiency_summary_json")) or _dict(plan.get("capital_plan_json"))
        coordinator = _dict(plan.get("coordinator_judgment_json"))
        risk_status = _status_from_summary(risk_summary, "risk")
        exit_status = _status_from_exit_plan(exit_plan_readiness) or _status_from_summary(exit_summary, "exit")
        capital_status = _status_from_summary(capital_summary, "capital")
        risk_evidence_candidate = self._risk_evidence.latest_for_plan(conn, plan)
        risk_evidence_truth = _risk_evidence_truth(risk_evidence_candidate)
        risk_evidence = risk_evidence_candidate if risk_evidence_truth["truth_state"] == "ACTIVE_FRESH" else None
        legacy_risk_truth = _legacy_risk_truth(conn, plan, risk_summary, self._truth)
        selected_risk_source = "LEGACY_RISK_DECISION"
        selected_risk_freshness = legacy_risk_truth["truth_state"]
        legacy_risk_ignored: list[str] = []
        final_risk_interpretation = risk_status
        if risk_evidence:
            selected_risk_source = "RISK_EVIDENCE_MESH"
            selected_risk_freshness = "ACTIVE_FRESH"
            risk_status = str(risk_evidence.get("risk_decision") or risk_status or "").upper() or risk_status
            final_risk_interpretation = risk_status
            risk_subtype = str(risk_evidence.get("risk_blocker_subtype") or "").upper()
            if risk_status == "RISK_BLOCK":
                critical.add("RISK_BLOCKED")
                if risk_subtype:
                    critical.add(risk_subtype)
            else:
                legacy_risk_ignored = sorted(critical & LEGACY_RISK_BLOCKERS)
                critical.difference_update(LEGACY_RISK_BLOCKERS)
                optional.update(str(item).upper() for item in _list(risk_evidence.get("optional_context_missing_json")) if str(item).upper() in OPTIONAL_CONTEXT)
                context.update(str(item).upper() for item in _list(risk_evidence.get("critical_evidence_missing_json")) if str(item).upper() in CONTEXT_DEPENDENT)
        elif risk_status in {"BLOCK", "REJECT", "REJECTED", "RISK_BLOCKED"}:
            critical.add("RISK_BLOCKED")
            critical.update(_risk_precision_blockers(risk_summary))
        if not risk_evidence and risk_evidence_candidate and legacy_risk_truth["truth_state"] != "ACTIVE_FRESH":
            selected_risk_source = "LAST_KNOWN_RISK_CONTEXT"
            selected_risk_freshness = risk_evidence_truth["truth_state"]
            critical.add("STALE_RISK_SOURCE_REFRESH_REQUIRED")
        if exit_status in {"BLOCK", "REJECT", "EXIT_BLOCKED"}:
            critical.add("EXIT_BLOCKED")
        elif request_action in {"PAPER_INTENT", "PAPER_EXECUTION"} and exit_status in {"INSUFFICIENT_DATA", "MISSING", "UNKNOWN", "EXIT_UNKNOWN", "EXIT_NOT_READY"}:
            critical.add("EXIT_BLOCKED")
            critical.add("EXIT_NOT_READY")
        if capital_status in {"BLOCK", "CAPITAL_BLOCKED"}:
            critical.add("CAPITAL_BLOCKED")
            critical.update(_capital_precision_blockers(capital_summary))

        freshness = self._freshness.evaluate_plan_with_conn(
            conn,
            plan,
            request_action=request_action,
            metadata=metadata,
            write_checks=request_action in {"PAPER_INTENT", "PAPER_EXECUTION"},
        )
        critical.update(str(item).upper() for item in _list(freshness.get("critical_blockers")))
        event_native_capital_truth = _event_native_capital_truth(conn, plan)
        if "STALE_CAPITAL_EVALUATION" in critical and event_native_capital_truth.get("fresh"):
            capital_opinion_state = str(event_native_capital_truth.get("capital_opinion_state") or "").upper()
            if capital_opinion_state == "CAPITAL_OK":
                critical.discard("STALE_CAPITAL_EVALUATION")
            elif capital_opinion_state == "CAPITAL_BLOCKED":
                critical.discard("STALE_CAPITAL_EVALUATION")
                critical.add("CAPITAL_BLOCKED")
                critical.update(str(item).upper() for item in _list(event_native_capital_truth.get("blockers")))
            elif capital_opinion_state in {"CAPITAL_MISSING", "CAPITAL_UNKNOWN", "CAPITAL_PARTIAL"}:
                critical.discard("STALE_CAPITAL_EVALUATION")
                critical.add("CAPITAL_SOURCE_MISSING")
        if risk_evidence and risk_status in {"RISK_REVIEW", "RISK_WATCH", "RISK_SUPPORT"}:
            freshness_legacy_risk = sorted(critical & LEGACY_RISK_BLOCKERS)
            if freshness_legacy_risk:
                legacy_risk_ignored = sorted(set(legacy_risk_ignored) | set(freshness_legacy_risk))
                critical.difference_update(LEGACY_RISK_BLOCKERS)

        actionability = "WATCH_FOR_CONFIRMATION"
        allow_intent = False
        allow_execution = False
        if critical:
            actionability = "HARD_BLOCK"
        elif plan_status == "NO_TRADE" or strategy_type == "NO_TRADE" or decision_class == "NO_TRADE":
            actionability = "NO_TRADE"
        elif plan_status == "INSUFFICIENT_DATA" or strategy_type == "INSUFFICIENT_DATA" or decision_class == "INSUFFICIENT_DATA":
            actionability = "WATCH_FOR_CONFIRMATION"
        elif request_action in {"PAPER_INTENT", "PAPER_EXECUTION"}:
            if self._paper_gate_inputs_clear(plan, metadata, same_market_status=same_market_status):
                actionability = "ACTIONABLE_STANDARD_PAPER" if plan_status == "COMPLETE" else "ACTIONABLE_SMALL_PAPER"
                allow_intent = request_action == "PAPER_INTENT"
                allow_execution = request_action == "PAPER_EXECUTION"
            else:
                actionability = "WATCH_FOR_CONFIRMATION"
        elif plan_status == "COMPLETE":
            actionability = "COMPLETE_HIGH_CONFIDENCE"
        elif not optional and not context and plan_status == "PARTIAL":
            actionability = "ACTIONABLE_SMALL_PAPER"

        reason = _reason(actionability, critical=critical, optional=optional, context=context, request_action=request_action)
        return {
            "actionability_class": actionability,
            "allow_paper_intent": allow_intent,
            "allow_paper_execution": allow_execution,
            "critical_blockers_json": sorted(critical),
            "optional_missing_json": sorted(optional),
            "context_dependent_missing_json": sorted(context),
            "mesh_contributions_count": _count_contributions(conn, str(plan.get("plan_id"))),
            "coordinator_decision_id": _text(coordinator.get("decision_id") or coordinator.get("coordinator_decision_id")),
            "same_market_guard_status": same_market_status,
            "capital_status": capital_status,
            "risk_status": risk_status,
            "exit_status": exit_status,
            "reason": reason,
            "metadata_json": {
                "request_action": request_action,
                "missing_input_classification": {
                    "critical": sorted(critical),
                    "optional": sorted(optional),
                    "context_dependent": sorted(context),
                    "unclassified": sorted(missing - critical - optional - context),
                },
                "freshness_governance": freshness,
                "blocker_precision": {
                    "risk": sorted(_risk_precision_blockers(risk_summary)),
                    "risk_evidence": _risk_evidence_summary(risk_evidence),
                    "capital": sorted(_capital_precision_blockers(capital_summary)),
                    "risk_capital": _risk_capital_summary(capital_summary, risk_evidence),
                    "exit": exit_plan_readiness,
                    "same_market": same_market_blocker,
                },
                "risk_capital_gate_trace": _risk_capital_summary(capital_summary, risk_evidence),
                "exit_readiness_trace": exit_plan_readiness,
                "risk_source_trace": {
                    "selected_risk_source": selected_risk_source,
                    "selected_risk_source_freshness": selected_risk_freshness,
                    "selected_risk_evidence_evaluation_id": (risk_evidence_candidate or {}).get("evaluation_id"),
                    "selected_risk_evidence_truth_state": risk_evidence_truth["truth_state"],
                    "selected_risk_evidence_age_seconds": risk_evidence_truth["age_seconds"],
                    "legacy_risk_decision_id": _dict(plan.get("source_refs_json")).get("risk_decision_id") or risk_summary.get("risk_decision_id"),
                    "legacy_risk_state": risk_summary.get("decision") or risk_summary.get("risk_status") or risk_status,
                    "legacy_risk_truth_state": legacy_risk_truth["truth_state"],
                    "legacy_ignored": bool(legacy_risk_ignored),
                    "ignored_legacy_risk_sources": legacy_risk_ignored,
                    "ignored_reason": _ignored_reason(legacy_risk_ignored),
                    "final_risk_interpretation": final_risk_interpretation,
                    "blockers_by_priority": sorted(critical),
                },
                "truth_state": {
                    "same_market_guard": same_market_truth,
                    "event_native_capital": event_native_capital_truth,
                },
                "derived_truth_only": True,
                "no_trading_mutation": True,
                **metadata,
            },
        }

    def _paper_gate_inputs_clear(self, plan: dict[str, Any], metadata: dict[str, Any], *, same_market_status: str | None) -> bool:
        if same_market_status != "ALLOW":
            return False
        if bool(metadata.get("risk_approved")) is False and metadata.get("risk_approved") is not None:
            return False
        if bool(metadata.get("exit_ready")) is False and metadata.get("exit_ready") is not None:
            return False
        if bool(metadata.get("lineage_trusted")) is False and metadata.get("lineage_trusted") is not None:
            return False
        if bool(metadata.get("not_dry_run")) is False and metadata.get("not_dry_run") is not None:
            return False
        if not plan.get("market_id") or not plan.get("side"):
            return False
        if str(plan.get("strategy_type") or "").upper() in BLOCKED_STRATEGIES:
            return False
        return True


def _upsert_decision(conn: Any, decision: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    params = {
        **decision,
        "critical_blockers_json": Jsonb(_json_safe(decision.get("critical_blockers_json") or [])),
        "optional_missing_json": Jsonb(_json_safe(decision.get("optional_missing_json") or [])),
        "context_dependent_missing_json": Jsonb(_json_safe(decision.get("context_dependent_missing_json") or [])),
        "metadata_json": Jsonb(_json_safe(decision.get("metadata_json") or {})),
    }
    conn.execute(
        """
        INSERT INTO lifecycle_governance_decisions (
            decision_id, subject_type, subject_id, lifecycle_plan_id, market_id, side, token_id,
            actionability_class, allow_paper_intent, allow_paper_execution, critical_blockers_json,
            optional_missing_json, context_dependent_missing_json, mesh_contributions_count,
            coordinator_decision_id, same_market_guard_status, capital_status, risk_status, exit_status,
            reason, metadata_json
        ) VALUES (
            %(decision_id)s,%(subject_type)s,%(subject_id)s,%(lifecycle_plan_id)s,%(market_id)s,%(side)s,%(token_id)s,
            %(actionability_class)s,%(allow_paper_intent)s,%(allow_paper_execution)s,%(critical_blockers_json)s,
            %(optional_missing_json)s,%(context_dependent_missing_json)s,%(mesh_contributions_count)s,
            %(coordinator_decision_id)s,%(same_market_guard_status)s,%(capital_status)s,%(risk_status)s,%(exit_status)s,
            %(reason)s,%(metadata_json)s
        )
        ON CONFLICT (decision_id) DO UPDATE SET
            actionability_class=EXCLUDED.actionability_class,
            allow_paper_intent=EXCLUDED.allow_paper_intent,
            allow_paper_execution=EXCLUDED.allow_paper_execution,
            critical_blockers_json=EXCLUDED.critical_blockers_json,
            optional_missing_json=EXCLUDED.optional_missing_json,
            context_dependent_missing_json=EXCLUDED.context_dependent_missing_json,
            mesh_contributions_count=EXCLUDED.mesh_contributions_count,
            coordinator_decision_id=EXCLUDED.coordinator_decision_id,
            same_market_guard_status=EXCLUDED.same_market_guard_status,
            capital_status=EXCLUDED.capital_status,
            risk_status=EXCLUDED.risk_status,
            exit_status=EXCLUDED.exit_status,
            reason=EXCLUDED.reason,
            metadata_json=EXCLUDED.metadata_json
        """,
        params,
    )
    for source in sources:
        conn.execute(
            """
            INSERT INTO lifecycle_governance_sources (decision_id,source_table,source_record_id,source_type,contribution_summary)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (decision["decision_id"], source["source_table"], str(source["source_record_id"]), source["source_type"], source["contribution_summary"]),
        )


def _sources_for_decision(plan: dict[str, Any], decision: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [
        {
            "source_table": "trade_lifecycle_plans",
            "source_record_id": plan.get("plan_id"),
            "source_type": "LIFECYCLE_PLAN",
            "contribution_summary": f"Lifecycle plan classified as {decision['actionability_class']}",
        }
    ]
    metadata = _dict(decision.get("metadata_json"))
    guard = _dict(metadata.get("same_market_guard_decision"))
    guard_id = guard.get("decision_id")
    if guard_id:
        sources.append(
            {
                "source_table": "same_market_side_guard_decisions",
                "source_record_id": guard_id,
                "source_type": "SAME_MARKET_GUARD",
                "contribution_summary": f"Same-market guard status {guard.get('decision')}",
            }
        )
    risk_trace = _dict(metadata.get("risk_source_trace"))
    risk_evidence_id = risk_trace.get("selected_risk_evidence_evaluation_id")
    if risk_evidence_id:
        sources.append(
            {
                "source_table": "risk_evidence_mesh_evaluations",
                "source_record_id": risk_evidence_id,
                "source_type": "RISK_EVIDENCE_MESH",
                "contribution_summary": f"Selected risk source {risk_trace.get('selected_risk_source')} with interpretation {risk_trace.get('final_risk_interpretation')}",
            }
        )
    return sources


def _latest_plans(conn: Any, *, subject_type: str | None, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "trade_lifecycle_plans"):
        return []
    where = "WHERE subject_type=%s" if subject_type else ""
    params: list[Any] = [subject_type] if subject_type else []
    params.append(limit)
    return _fetchall(conn, f"SELECT * FROM trade_lifecycle_plans {where} ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC LIMIT %s", tuple(params))


def _decision_id(plan: dict[str, Any], classified: dict[str, Any], request_action: str) -> str:
    return _stable_decision_id(
        str(plan["subject_type"]),
        str(plan["subject_id"]),
        str(plan.get("plan_id") or ""),
        request_action,
        str(classified["actionability_class"]),
        classified.get("critical_blockers_json") or [],
    )


def _stable_decision_id(subject_type: str, subject_id: str, plan_id: str | None, request_action: str, actionability: str, blockers: list[str]) -> str:
    raw = "|".join([subject_type, subject_id, str(plan_id or ""), request_action, actionability, ",".join(sorted(str(item) for item in blockers))])
    return f"lifecycle_governance_{uuid5(NAMESPACE_URL, raw).hex}"


def _blocked_reason_from_plan(plan: dict[str, Any]) -> str:
    strategy = str(plan.get("strategy_type") or "").upper()
    if strategy in BLOCKED_STRATEGIES:
        return BLOCKED_STRATEGIES[strategy]
    missing = {str(item).upper() for item in _list(plan.get("missing_inputs_json"))}
    for item in sorted(missing):
        if item in CRITICAL_BLOCKERS:
            return item
    return "LIFECYCLE_PLAN_BLOCKED"


def _risk_evidence_truth(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"truth_state": "MISSING", "age_seconds": None, "ttl_seconds": RISK_EVIDENCE_TTL_SECONDS}
    age = _age_seconds(row.get("updated_at") or row.get("created_at"))
    if age is not None and age <= RISK_EVIDENCE_TTL_SECONDS:
        state = "ACTIVE_FRESH"
    elif age is None:
        state = "UNKNOWN"
    else:
        state = "LAST_KNOWN"
    return {"truth_state": state, "age_seconds": age, "ttl_seconds": RISK_EVIDENCE_TTL_SECONDS}


def _legacy_risk_truth(conn: Any, plan: dict[str, Any], risk_summary: dict[str, Any], truth_service: TruthStateService) -> dict[str, Any]:
    risk_id = _dict(plan.get("source_refs_json")).get("risk_decision_id") or risk_summary.get("risk_decision_id")
    timestamp = risk_summary.get("updated_at") or risk_summary.get("created_at")
    if risk_id and _table_exists(conn, "risk_decisions"):
        row = _fetchone(conn, "SELECT COALESCE(updated_at,created_at) AS risk_at FROM risk_decisions WHERE risk_decision_id=%s ORDER BY updated_at DESC NULLS LAST,id DESC LIMIT 1", (str(risk_id),))
        timestamp = (row or {}).get("risk_at") or timestamp
    if not risk_id and not timestamp:
        return {"truth_state": "UNKNOWN", "decision_permission": "UNKNOWN_PERMISSION", "age_seconds": None}
    return truth_service.classify_source(source_type="RISK_DECISION", created_at_source=timestamp, updated_at_source=timestamp)


def _ignored_reason(legacy_risk_ignored: list[str]) -> str | None:
    if not legacy_risk_ignored:
        return None
    if any(item in {"RISK_BLOCKED", "STALE_RISK_DECISION"} or item.startswith("RISK_BLOCKED") for item in legacy_risk_ignored):
        return "Fresh non-blocking Risk Evidence Mesh evaluation selected over stale legacy risk block sources."
    return "Fresh non-blocking Risk Evidence Mesh evaluation selected over legacy risk blockers."


def _risk_precision_blockers(summary: dict[str, Any]) -> set[str]:
    blockers = {str(item).upper() for item in _list(summary.get("blockers"))}
    reasons = blockers | {str(item).upper() for item in _list(summary.get("risk_reasons"))}
    precise: set[str] = set()
    if any("LIQUIDITY" in item for item in reasons):
        precise.add("RISK_BLOCKED_BAD_LIQUIDITY")
    if any("SPREAD" in item for item in reasons):
        precise.add("RISK_BLOCKED_SPREAD")
    if any("STALE" in item for item in reasons):
        precise.add("RISK_BLOCKED_STALE_DATA")
    if any(item in {"MISSING_TRUSTED_ORDERBOOK", "NO_TRUSTED_ORDERBOOK", "CLOB_NO_BOOK"} for item in reasons):
        precise.add("RISK_BLOCKED_NO_TRUSTED_ORDERBOOK")
    if any("EXECUTABLE_PRICE" in item for item in reasons):
        precise.add("RISK_BLOCKED_MISSING_EXECUTABLE_PRICE")
    if any("CONFIDENCE" in item for item in reasons):
        precise.add("RISK_BLOCKED_LOW_CONFIDENCE")
    if any(item in {"NO_EDGE", "THESIS_BLOCKED"} for item in reasons):
        precise.add("RISK_BLOCKED_NO_EDGE")
    if any("LINEAGE" in item or "MARKET_LINK" in item for item in reasons):
        precise.add("RISK_BLOCKED_LINEAGE")
    if not precise and (str(summary.get("decision") or "").upper() == "BLOCK" or str(summary.get("risk_status") or "").upper() == "BLOCKED"):
        precise.add("RISK_BLOCKED_UNKNOWN")
    return precise


def _risk_evidence_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
    edge_thesis = metadata.get("edge_thesis") if isinstance(metadata.get("edge_thesis"), dict) else {}
    return {
        "evaluation_id": row.get("evaluation_id"),
        "risk_decision": row.get("risk_decision"),
        "risk_blocker_subtype": row.get("risk_blocker_subtype"),
        "edge_source_type": row.get("edge_source_type"),
        "edge_status": row.get("edge_status"),
        "source_refresh_cycle_id": metadata.get("source_refresh_cycle_id") or edge_thesis.get("source_refresh_cycle_id"),
        "edge_thesis_id": edge_thesis.get("edge_thesis_id"),
        "propagation_context": metadata.get("propagation_context") or edge_thesis.get("propagation_context") or {},
        "critical_missing": row.get("critical_evidence_missing_json"),
        "optional_missing": row.get("optional_context_missing_json"),
        "blocking_evidence": row.get("blocking_evidence_json"),
    }


def _capital_precision_blockers(summary: dict[str, Any]) -> set[str]:
    text = " ".join(str(value or "") for value in (summary.get("recommendation"), summary.get("reason"), summary.get("status"))).upper()
    missing = {str(item).upper() for item in _list(summary.get("missing_inputs"))}
    precise: set[str] = set()
    if "RECONCILIATION" in text:
        precise.add("CAPITAL_BLOCKED_RECONCILIATION")
    if "BALANCE" in text or "INSUFFICIENT" in text:
        precise.add("CAPITAL_BLOCKED_INSUFFICIENT_BALANCE")
    if "EXPOSURE" in text:
        precise.add("CAPITAL_BLOCKED_MAX_EXPOSURE")
    if "OPEN_POSITION" in text:
        precise.add("CAPITAL_BLOCKED_MAX_OPEN_POSITIONS")
    if "DAILY_LOSS" in text or "DAILY LOSS" in text:
        precise.add("CAPITAL_BLOCKED_DAILY_LOSS")
    if not precise and str(summary.get("recommendation") or "").upper() == "CAPITAL_BLOCK":
        precise.add("CAPITAL_INSUFFICIENT_DATA" if missing else "CAPITAL_BLOCKED")
    return precise


def _event_native_capital_truth(conn: Any, plan: dict[str, Any], *, ttl_seconds: int = 600) -> dict[str, Any]:
    if not _table_exists(conn, "brain_outputs"):
        return {"fresh": False, "reason": "BRAIN_OUTPUTS_MISSING"}
    subject_type = str(plan.get("subject_type") or "").upper()
    candidate_id = str(plan.get("subject_id") or "") if subject_type == "PAPER_CANDIDATE" else None
    market_id = _text(plan.get("market_id"))
    side = _text(plan.get("side"))
    token_id = _text(plan.get("token_id"))
    clauses = ["brain = 'capital'", "metadata_json->>'event_native_state' = 'EVENT_NATIVE'"]
    params: list[Any] = []
    if candidate_id:
        clauses.append("metadata_json->>'candidate_id' = %s")
        params.append(candidate_id)
    elif market_id:
        clauses.append("market_id = %s")
        params.append(market_id)
    else:
        return {"fresh": False, "reason": "NO_CANDIDATE_OR_MARKET"}
    if side:
        clauses.append("(metadata_json->>'side' IS NULL OR upper(metadata_json->>'side') = %s)")
        params.append(side.upper())
    if token_id:
        clauses.append("(metadata_json->>'token_id' IS NULL OR metadata_json->>'token_id' = %s)")
        params.append(token_id)
    row = _fetchone(
        conn,
        f"""
        SELECT brain_output_id, market_id, correlation_id, metadata_json, created_at,
               EXTRACT(EPOCH FROM (now() - created_at)) AS age_seconds
        FROM brain_outputs
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    if not row:
        return {"fresh": False, "reason": "NO_EVENT_NATIVE_CAPITAL_OUTPUT"}
    metadata = _dict(row.get("metadata_json"))
    age = row.get("age_seconds")
    fresh = age is not None and float(age) <= ttl_seconds
    return _json_safe(
        {
            "fresh": fresh,
            "reason": "FRESH_EVENT_NATIVE_CAPITAL" if fresh else "EVENT_NATIVE_CAPITAL_STALE",
            "brain_output_id": row.get("brain_output_id"),
            "correlation_id": row.get("correlation_id"),
            "capital_opinion_state": metadata.get("capital_opinion_state"),
            "available_capital": metadata.get("available_capital"),
            "locked_capital": metadata.get("locked_capital"),
            "open_exposure": metadata.get("open_exposure"),
            "blockers": metadata.get("blockers") or [],
            "warnings": metadata.get("warnings") or [],
            "age_seconds": float(age) if age is not None else None,
            "ttl_seconds": ttl_seconds,
        }
    )


def _same_market_truth(truth_service: TruthStateService, conn: Any, plan: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
    if not guard:
        return {}
    guard_id = _text(guard.get("decision_id") or _dict(plan.get("source_refs_json")).get("same_market_guard_decision_id"))
    timestamp = guard.get("created_at")
    if not timestamp and guard_id and _table_exists(conn, "same_market_side_guard_decisions"):
        row = _fetchone(conn, "SELECT created_at FROM same_market_side_guard_decisions WHERE decision_id=%s", (guard_id,))
        timestamp = (row or {}).get("created_at")
    metadata = {
        "decision": guard.get("decision") or guard.get("status"),
        "blocker_reason": guard.get("blocker_reason"),
        "source_layer": "lifecycle_governance",
    }
    return truth_service.decision_permission_for_source(
        conn,
        source_table="same_market_side_guard_decisions",
        source_record_id=guard_id,
        source_type="SAME_MARKET_GUARD",
        timestamp=timestamp,
        metadata=metadata,
        write=_table_exists(conn, "truth_state_registry"),
    )


def _reason(actionability: str, *, critical: set[str], optional: set[str], context: set[str], request_action: str) -> str:
    if actionability == "HARD_BLOCK":
        return f"{request_action} blocked by critical lifecycle governance blockers: {', '.join(sorted(critical))}"
    if actionability == "NO_TRADE":
        return f"{request_action} denied because lifecycle plan is NO_TRADE."
    if actionability == "WATCH_FOR_CONFIRMATION":
        missing = sorted(optional | context)
        suffix = f" Missing or context-dependent inputs: {', '.join(missing)}." if missing else ""
        return f"{request_action} held for confirmation; no critical blocker cleared it into Paper authorization.{suffix}"
    if actionability == "ACTIONABLE_SMALL_PAPER":
        return f"{request_action} allowed as ACTIONABLE_SMALL_PAPER; critical blockers are clear and optional context is non-blocking."
    if actionability == "ACTIONABLE_STANDARD_PAPER":
        return f"{request_action} allowed as ACTIONABLE_STANDARD_PAPER; lifecycle plan is complete enough for normal Paper sizing."
    return f"{request_action} classified as COMPLETE_HIGH_CONFIDENCE."


def _status_from_summary(summary: dict[str, Any], prefix: str) -> str | None:
    for key in ("status", "decision", "recommendation", "stance", "final_action", "final_stance"):
        value = summary.get(key)
        if value not in (None, "", []):
            return str(value).upper()
    if not summary:
        return f"{prefix.upper()}_MISSING"
    return None


def _exit_plan_readiness_summary(conn: Any, plan: dict[str, Any]) -> dict[str, Any]:
    if conn is None:
        return {}
    if not _table_exists(conn, "exit_plans"):
        return {"status": "EXIT_PLAN_TABLE_MISSING", "classification": "UNKNOWN_BUG", "source": "exit_plans"}
    refs = _dict(plan.get("source_refs_json"))
    candidates: list[str] = []
    for value in (refs.get("exit_plan_id"),):
        text = _text(value)
        if text:
            candidates.append(text)
    if str(plan.get("subject_type") or "").upper() == "PAPER_CANDIDATE" and plan.get("subject_id"):
        candidates.append(f"exit_candidate_{plan['subject_id']}")
    row = None
    for exit_plan_id in dict.fromkeys(candidates):
        row = _fetchone(conn, "SELECT * FROM exit_plans WHERE exit_plan_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (exit_plan_id,))
        if row:
            break
    if row is None:
        risk_ref = _text(refs.get("risk_decision_id") or _dict(plan.get("risk_summary_json")).get("risk_decision_id"))
        if risk_ref:
            row = _fetchone(conn, "SELECT * FROM exit_plans WHERE risk_decision_ref=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (risk_ref,))
    if row is None:
        return {
            "status": "EXIT_PLAN_MISSING",
            "classification": "MISSING_SAFE_COMPUTE_PATH",
            "source": "exit_plans",
            "required_to_pass": ["Build a candidate-specific exit plan from fresh orderbook and risk evidence."],
        }
    blockers = [str(item).upper() for item in _list(row.get("blockers"))]
    missing = [str(item).upper() for item in _list(row.get("missing_exit_evidence"))]
    raw_status = str(row.get("status") or row.get("plan_status") or "").upper()
    ready = bool(row.get("paper_exit_ready")) and raw_status == "COMPLETE" and not blockers and not missing
    if ready:
        status = "EXIT_READY"
        classification = "READY"
        required: list[str] = []
    elif raw_status == "BLOCKED" or blockers:
        status = "EXIT_BLOCKED"
        classification = "CURRENT_REAL_BLOCKER"
        required = ["Clear current exit blockers without bypassing Risk or liquidity gates."]
    else:
        status = "EXIT_NOT_READY"
        classification = "CURRENT_REAL_BLOCKER"
        required = ["Refresh candidate-specific exit plan with entry, exit, spread, depth, and liquidity evidence."]
    liquidity = _dict(row.get("liquidity_exit_check"))
    return {
        "status": status,
        "raw_status": raw_status,
        "plan_status": row.get("plan_status"),
        "exit_plan_id": row.get("exit_plan_id"),
        "paper_exit_ready": bool(row.get("paper_exit_ready")),
        "blockers": blockers,
        "missing_exit_evidence": missing,
        "classification": classification,
        "entry_price": row.get("entry_price"),
        "exit_price": row.get("target_exit"),
        "stop_loss": row.get("stop_loss"),
        "spread": liquidity.get("current_spread"),
        "liquidity_score": liquidity.get("current_liquidity_score"),
        "orderbook_snapshot_id": row.get("orderbook_snapshot_id"),
        "source_records": [{"source_table": "exit_plans", "source_record_id": row.get("exit_plan_id")}],
        "required_to_pass": required,
        "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at"),
    }


def _status_from_exit_plan(summary: dict[str, Any]) -> str | None:
    status = str(summary.get("status") or "").upper()
    if status in {"EXIT_READY", "EXIT_BLOCKED", "EXIT_NOT_READY"}:
        return status
    return None


def _risk_capital_summary(capital_summary: dict[str, Any], risk_evidence: dict[str, Any] | None) -> dict[str, Any]:
    risk_blockers = [str(item).upper() for item in _list((risk_evidence or {}).get("blocking_evidence_json"))]
    recommendation = str(capital_summary.get("recommendation") or "").upper()
    missing = [str(item).upper() for item in _list(capital_summary.get("missing_inputs") or capital_summary.get("missing_inputs_json"))]
    metadata = _dict(capital_summary.get("metadata_json") or capital_summary.get("metadata"))
    thesis_trace = _dict(metadata.get("trade_thesis_trace"))
    blocker = "RISK_BLOCKED_CAPITAL" if "RISK_BLOCKED_CAPITAL" in risk_blockers or recommendation == "CAPITAL_BLOCK" else None
    if blocker:
        classification = "CURRENT_REAL_BLOCKER" if not missing else "POLICY_MISMATCH"
        required = [
            "Improve capital efficiency score, reward-per-dollar-hour, liquidity quality, or capital/reward evidence under existing policy.",
            "Provide a supported trade thesis with explicit exit intent when using early-exit hold time.",
        ]
    elif recommendation in {"CAPITAL_SUPPORT", "CAPITAL_WATCH"}:
        classification = "PASSED"
        required = []
    elif recommendation == "CAPITAL_INSUFFICIENT_DATA":
        classification = "POLICY_MISMATCH"
        required = ["Provide capital locked and potential reward evidence for the candidate-specific risk-capital policy."]
    else:
        classification = "UNKNOWN_BUG" if risk_evidence else "UNKNOWN"
        required = ["Provide current risk-capital evidence."]
    return {
        "risk_result": (risk_evidence or {}).get("risk_decision"),
        "risk_capital_blocker": blocker,
        "capital_gate_state": recommendation or None,
        "risk_capital_policy_state": recommendation or None,
        "capital_efficiency_score": capital_summary.get("capital_efficiency_score"),
        "reward_per_dollar_hour": capital_summary.get("reward_per_dollar_hour"),
        "trade_thesis_trace": thesis_trace,
        "trade_thesis_type": thesis_trace.get("trade_thesis_type"),
        "exit_intent": thesis_trace.get("exit_intent"),
        "expected_hold_time_hours": thesis_trace.get("thesis_expected_hold_time_hours"),
        "hold_time_source": thesis_trace.get("hold_time_source"),
        "dynamic_hold_time_applied": thesis_trace.get("dynamic_hold_time_applied"),
        "original_reward_per_dollar_hour": thesis_trace.get("original_reward_per_dollar_hour"),
        "dynamic_reward_per_dollar_hour": thesis_trace.get("dynamic_reward_per_dollar_hour"),
        "capital_locked": capital_summary.get("capital_locked"),
        "missing_inputs": missing,
        "classification": classification,
        "source_records": [{"source_table": "capital_efficiency_evaluations", "source_record_id": capital_summary.get("evaluation_id")}] if capital_summary.get("evaluation_id") else [],
        "required_to_pass": required,
    }


def _count_contributions(conn: Any, plan_id: str) -> int:
    if not plan_id or not _table_exists(conn, "trade_lifecycle_brain_contributions"):
        return 0
    row = _fetchone(conn, "SELECT COUNT(*) AS count FROM trade_lifecycle_brain_contributions WHERE plan_id=%s", (plan_id,))
    return _int((row or {}).get("count"))


def _top_jsonb_values(conn: Any, column: str, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "lifecycle_governance_decisions"):
        return []
    return _fetchall(
        conn,
        f"""
        SELECT value AS item, COUNT(*) AS count
        FROM lifecycle_governance_decisions, jsonb_array_elements_text({column}) AS value
        GROUP BY value
        ORDER BY count DESC, item
        LIMIT %s
        """,
        (limit,),
    )


def _tables_ready(conn: Any) -> bool:
    return _table_exists(conn, "trade_lifecycle_plans") and _table_exists(conn, "lifecycle_governance_decisions") and _table_exists(conn, "lifecycle_governance_sources")


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _fetchone(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _safety_counts(conn: Any) -> dict[str, Any]:
    counts = {
        table: _count_table(conn, table)
        for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions")
    }
    account = _fetchone(conn, "SELECT current_balance,available_balance,locked_balance,open_exposure,realized_pnl,unrealized_pnl FROM paper_accounts WHERE account_id='paper_default'") if _table_exists(conn, "paper_accounts") else None
    counts["capital_balances"] = _json_safe(account) if account else None
    return counts


def _empty_dashboard(status: str, generated_at: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "generated_at": generated_at,
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        "total_decisions": 0,
        "decisions_by_actionability": {},
        "allow_paper_intent_count": 0,
        "allow_paper_execution_count": 0,
        "hard_block_count": 0,
        "no_trade_count": 0,
        "watch_count": 0,
        "actionable_small_paper_count": 0,
        "actionable_standard_paper_count": 0,
        "complete_high_confidence_count": 0,
        "critical_blockers_top": [],
        "optional_missing_top": [],
        "risk_evidence_used_count": 0,
        "legacy_risk_ignored_count": 0,
        "stale_legacy_risk_block_ignored_count": 0,
        "risk_review_promoted_to_watch_count": 0,
        "risk_review_kept_blocked_count": 0,
        "risk_review_actionable_count": 0,
        "risk_source_selection_summary": [],
        "latest_risk_review_traces": [],
        "bypass_paths_found": [],
        "latest_decisions": [],
    }


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    return str(value)


def _age_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return max(0, int((datetime.now(UTC) - value.astimezone(UTC)).total_seconds()))
    return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
