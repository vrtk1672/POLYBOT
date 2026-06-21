from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.exit_foundation import ExitFoundationPlan, ExitFoundationRun
from app.repositories.exit_foundation_repository import ExitFoundationRepository, exit_plan_from_row
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.exit_hold_reasoning import ExitHoldReasoningService
from app.services.payout_odds import PayoutOddsService
from app.services.trade_lifecycle import TradeLifecycleService


MAX_HOLD_SECONDS_DEFAULT = 3600
MAX_SPREAD = 0.08
MIN_LIQUIDITY_SCORE = 0.25
ORDERBOOK_STALE_SECONDS = 120


class ExitFoundationService:
    """Risk-derived, non-executing Exit Foundation.

    This service intentionally does not call the legacy Exit Cortex evaluator because
    that path can create executable exit intents. 4C-Q only persists plan contracts.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: ExitFoundationRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or ExitFoundationRepository()

    def build_exit_plans(
        self,
        *,
        limit: int = 100,
        include_blocked: bool = True,
        write_plans: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"exit_foundation_{uuid4().hex}"
        safety_before = _safety_counts(self._factory)
        rows: list[dict[str, Any]] = []
        if self._factory.enabled:
            with self._factory.connect() as conn:
                rows = self._repository.list_runtime_risk_decisions(conn, limit=limit, include_blocked=include_blocked)

        plans: list[ExitFoundationPlan] = []
        errors: list[str] = []
        for row in rows:
            try:
                plans.append(_plan_from_risk(row))
            except Exception as exc:
                errors.append(f"{row.get('risk_decision_id') or 'unknown'}:{type(exc).__name__}:{exc}")

        created = 0
        updated = 0
        if write_plans and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                for plan in plans:
                    _, was_created = self._repository.upsert_plan(conn, plan)
                    self._repository.record_rules(conn, plan)
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1

        safety_after = _safety_counts(self._factory)
        run = ExitFoundationRun(
            run_id=run_id,
            status="ERROR" if errors and not plans else "PARTIAL" if errors else "OK",
            risk_decisions_checked=len(rows),
            exit_plans_created=created,
            exit_plans_updated=updated,
            complete_exit_count=len([item for item in plans if item.status == "COMPLETE"]),
            incomplete_exit_count=len([item for item in plans if item.status == "INCOMPLETE"]),
            blocked_exit_count=len([item for item in plans if item.status == "BLOCKED"]),
            missing_market_count=len([item for item in plans if "MISSING_MARKET_ID" in item.missing_exit_evidence or "MISSING_MARKET_ID" in item.blockers]),
            missing_orderbook_count=len([item for item in plans if "MISSING_FRESH_ORDERBOOK" in item.missing_exit_evidence or "MISSING_FRESH_ORDERBOOK" in item.blockers]),
            missing_side_count=len([item for item in plans if "MISSING_SIDE" in item.missing_exit_evidence or "MISSING_SIDE" in item.blockers]),
            missing_risk_approval_count=len([item for item in plans if "MISSING_RISK_APPROVAL" in item.missing_exit_evidence or "MISSING_RISK_APPROVAL" in item.blockers]),
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            fills_created=max(0, safety_after["fills"] - safety_before["fills"]),
            positions_created=max(0, safety_after["positions"] - safety_before["positions"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            plans=plans,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary="; ".join(errors) if errors else None,
        )
        if write_plans and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
        return run.to_api_dict()

    def build_candidate_exit_plan_with_conn(
        self,
        conn: Any,
        *,
        candidate_id: str,
        event_id: str | None = None,
        correlation_id: str | None = None,
        write_plan: bool = True,
    ) -> dict[str, Any]:
        row = _candidate_exit_row(conn, candidate_id)
        if not row:
            return {"status": "SUBJECT_NOT_FOUND", "candidate_id": candidate_id, "plan_created": False}
        plan = _plan_from_candidate(row, event_id=event_id, correlation_id=correlation_id)
        if write_plan:
            self._repository.upsert_plan(conn, plan)
            self._repository.record_rules(conn, plan)
        return {
            "status": "OK",
            "candidate_id": candidate_id,
            "exit_plan_id": plan.exit_plan_id,
            "plan_status": plan.status,
            "exit_type": plan.exit_type,
            "paper_exit_ready": plan.paper_exit_ready,
            "blockers": plan.blockers,
            "missing_exit_evidence": plan.missing_exit_evidence,
            "plan_created": bool(write_plan),
        }

    def list_recent(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        market_id: str | None = None,
        risk_decision_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "OK", "count": 0, "exit_plans": []}
        with self._factory.connect() as conn:
            rows = self._repository.list_plans(conn, limit=limit, status=status, market_id=market_id, risk_decision_id=risk_decision_id)
        plans = [exit_plan_from_row(row).to_api_dict() for row in rows]
        return {"mock_data": False, "status": "OK", "count": len(plans), "exit_plans": plans}

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "exit_plans"):
                return _empty_summary()
            summary = self._repository.summary(conn, limit=limit)
            payout_odds = PayoutOddsService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            exit_hold = ExitHoldReasoningService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
            trade_lifecycle = TradeLifecycleService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
        latest_run = summary.get("latest_run") or {}
        missing_summary = summary.get("missing_exit_evidence_summary", [])
        return {
            "mock_data": False,
            "status": "OK",
            "latest_run": _json_safe(latest_run) if latest_run else None,
            "total_exit_plans": _int(summary.get("total_exit_plans")),
            "complete_exit_plans": _int(summary.get("complete_exit_plans")),
            "incomplete_exit_plans": _int(summary.get("incomplete_exit_plans")),
            "blocked_exit_plans": _int(summary.get("blocked_exit_plans")),
            "paper_exit_ready_count": _int(summary.get("paper_exit_ready_count")),
            "paper_intent_allowed_count": _int(summary.get("paper_intent_allowed_count")),
            "execution_allowed_count": _int(summary.get("execution_allowed_count")),
            "missing_market_count": _missing_count(missing_summary, "MISSING_MARKET_ID"),
            "missing_orderbook_count": _missing_count(missing_summary, "MISSING_FRESH_ORDERBOOK"),
            "missing_side_count": _missing_count(missing_summary, "MISSING_SIDE"),
            "missing_risk_approval_count": _missing_count(missing_summary, "MISSING_RISK_APPROVAL"),
            "top_exit_blockers": [_json_safe(row) for row in summary.get("top_exit_blockers", [])],
            "target_exit_count": _int(summary.get("target_exit_count")),
            "stop_loss_count": _int(summary.get("stop_loss_count")),
            "max_hold_seconds_default": MAX_HOLD_SECONDS_DEFAULT,
            "emergency_exit_rules_count": _int(summary.get("emergency_exit_rules_count")),
            "liquidity_exit_check_count": _int(summary.get("liquidity_exit_check_count")),
            "missing_exit_evidence_summary": [_json_safe(row) for row in missing_summary],
            "invalidation_rule_summary": [_json_safe(row) for row in summary.get("invalidation_rule_summary", [])],
            "emergency_exit_summary": [_json_safe(row) for row in summary.get("emergency_exit_summary", [])],
            "latest_exit_plans": [_json_safe(exit_plan_from_row(row).to_api_dict()) for row in summary.get("latest_exit_plans", [])],
            "paper_ready": False,
            "orders_created": _int(latest_run.get("orders_created")) if latest_run else 0,
            "order_intents_created": _int(latest_run.get("order_intents_created")) if latest_run else 0,
            "fills_created": _int(latest_run.get("fills_created")) if latest_run else 0,
            "positions_created": _int(latest_run.get("positions_created")) if latest_run else 0,
            "live_actions_created": _int(latest_run.get("live_actions_created")) if latest_run else 0,
            "remaining_blockers": [],
            "analysis_status": "OK",
            "payout_odds_visibility": payout_odds,
            "payout_odds_observational_only": True,
            "exit_hold_visibility": exit_hold,
            "exit_hold_observational_only": True,
            "capital_efficiency_visibility": capital_efficiency,
            "capital_efficiency_observational_only": True,
            "trade_lifecycle_visibility": trade_lifecycle,
            "trade_lifecycle_observational_only": True,
            "last_updated": datetime.now(UTC).isoformat(),
        }


def _plan_from_risk(row: dict[str, Any]) -> ExitFoundationPlan:
    risk_decision_id = str(row["risk_decision_id"])
    decision = str(row.get("decision") or "ERROR").upper()
    risk_status = str(row.get("risk_status") or "ERROR").upper()
    side = _normalize_side(row.get("thesis_side"))
    market_id = str(row["market_id"]) if row.get("market_id") else None
    orderbook_id = int(row["orderbook_snapshot_id"]) if row.get("orderbook_snapshot_id") is not None else None
    risk_approved = bool(row.get("risk_approved"))
    blockers = {str(item).upper() for item in _list(row.get("blockers"))}
    warnings = {str(item).upper() for item in _list(row.get("warnings"))}
    missing = {str(item).upper() for item in _list(row.get("required_missing_evidence"))}
    missing.update(str(item).upper() for item in _list(row.get("thesis_missing_evidence")))

    if decision == "BLOCK":
        blockers.add("RISK_BLOCKED")
    if decision == "REJECT":
        blockers.add("RISK_REJECTED")
    if decision == "ERROR" or risk_status == "ERROR":
        blockers.add("RISK_ERROR")
    if not market_id:
        missing.add("MISSING_MARKET_ID")
        blockers.add("MISSING_MARKET_ID")
    if not side:
        missing.add("MISSING_SIDE")
        blockers.add("MISSING_SIDE")
    if not risk_approved:
        missing.add("MISSING_RISK_APPROVAL")
        blockers.add("MISSING_RISK_APPROVAL")
    if orderbook_id is None or bool(row.get("orderbook_is_stale")) or str(row.get("orderbook_snapshot_status") or "").upper() in {"STALE", "ERROR", "EMPTY", "PARTIAL"}:
        missing.add("MISSING_FRESH_ORDERBOOK")
        blockers.add("MISSING_FRESH_ORDERBOOK")

    mid = _mid_price(row)
    if mid is None:
        missing.add("MISSING_MID_PRICE")
        blockers.add("MISSING_MID_PRICE")
    target_exit, stop_loss = _target_stop(side=side, mid=mid)

    if blockers & {"RISK_BLOCKED", "RISK_REJECTED", "RISK_ERROR"}:
        status = "BLOCKED"
        exit_type = "BLOCKED_NO_ENTRY_EXIT"
    elif missing:
        status = "INCOMPLETE"
        exit_type = "LIQUIDITY_PROTECTION_EXIT" if "MISSING_FRESH_ORDERBOOK" in missing else "TIME_ONLY_EXIT"
    else:
        status = "COMPLETE"
        exit_type = "BASIC_PROTECTIVE_EXIT"

    paper_exit_ready = status == "COMPLETE"
    if status == "COMPLETE" and (target_exit is None or stop_loss is None):
        status = "INCOMPLETE"
        exit_type = "TIME_ONLY_EXIT"
        paper_exit_ready = False
        missing.add("MISSING_TARGET_OR_STOP")
        blockers.add("MISSING_TARGET_OR_STOP")

    return ExitFoundationPlan(
        exit_plan_id=f"exit_{risk_decision_id}",
        thesis_id=str(row["thesis_id"]) if row.get("thesis_id") else None,
        risk_decision_id=risk_decision_id,
        market_id=market_id,
        side=side,
        status=status,
        exit_type=exit_type,
        target_exit=target_exit,
        stop_loss=stop_loss,
        max_hold_seconds=MAX_HOLD_SECONDS_DEFAULT,
        invalidation_rules=_invalidation_rules(),
        emergency_exit_rules=_emergency_exit_rules(),
        liquidity_exit_check={
            "max_spread": MAX_SPREAD,
            "min_liquidity_score": MIN_LIQUIDITY_SCORE,
            "stale_threshold_seconds": ORDERBOOK_STALE_SECONDS,
            "current_spread": _maybe_float(row.get("orderbook_spread")),
            "current_liquidity_score": _maybe_float(row.get("orderbook_liquidity_score")),
            "orderbook_snapshot_status": row.get("orderbook_snapshot_status"),
        },
        time_exit_check={
            "max_hold_seconds": MAX_HOLD_SECONDS_DEFAULT,
            "policy": "time_exit_required_before_any_entry",
        },
        missing_exit_evidence=sorted(missing),
        blockers=sorted(blockers),
        warnings=sorted(warnings | {"PAPER_INTENT_GATE_MISSING", "PAPER_READY_FALSE"}),
        source_risk_status=risk_status,
        source_risk_score=_maybe_float(row.get("risk_score")),
        orderbook_snapshot_id=orderbook_id,
        paper_intent_allowed=False,
        paper_exit_ready=paper_exit_ready,
        execution_allowed=False,
        generated_by="runtime",
        producer_name="exit_foundation",
        is_runtime_generated=True,
        is_dry_run_generated=False,
    )


def _candidate_exit_row(conn: Any, candidate_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return None
    row = conn.execute(
        """
        SELECT
            pec.eligibility_id,
            pec.market_id,
            pec.side,
            mv2.condition_id,
            COALESCE(
                NULLIF(pec.expected_token_id, ''),
                NULLIF(obs.token_id, ''),
                CASE
                    WHEN upper(pec.side) = 'YES' THEN NULLIF(mv2.yes_token_id, '')
                    WHEN upper(pec.side) = 'NO' THEN NULLIF(mv2.no_token_id, '')
                    ELSE NULL
                END
            ) AS token_id,
            pec.risk_decision_id,
            pec.exit_plan_id,
            pec.evidence,
            obs.id AS orderbook_snapshot_pk,
            obs.orderbook_snapshot_id,
            obs.best_bid AS orderbook_best_bid,
            obs.best_ask AS orderbook_best_ask,
            obs.mid_price AS orderbook_mid_price,
            obs.spread AS orderbook_spread,
            obs.liquidity_score AS orderbook_liquidity_score,
            obs.is_stale AS orderbook_is_stale,
            obs.snapshot_status AS orderbook_snapshot_status,
            obs.collected_at AS orderbook_collected_at,
            rem.risk_decision AS risk_evidence_decision,
            rem.risk_blocker_subtype AS risk_evidence_blocker,
            rem.evidence_quality_score AS risk_evidence_score,
            rem.evaluation_id AS risk_evidence_id
        FROM paper_eligibility_candidates pec
        LEFT JOIN markets_v2 mv2 ON mv2.market_id = pec.market_id
        LEFT JOIN LATERAL (
            SELECT book.*
            FROM orderbook_snapshots book
            WHERE (
                    pec.orderbook_snapshot_id IS NOT NULL
                    AND (book.id::text = pec.orderbook_snapshot_id::text OR book.orderbook_snapshot_id = pec.orderbook_snapshot_id::text)
                  )
               OR book.metadata_json->>'candidate_id' = pec.eligibility_id
            ORDER BY COALESCE(book.collected_at, book.snapshot_at, book.created_at) DESC, book.id DESC
            LIMIT 1
        ) obs ON true
        LEFT JOIN LATERAL (
            SELECT *
            FROM risk_evidence_mesh_evaluations
            WHERE subject_type='PAPER_CANDIDATE'
              AND subject_id=pec.eligibility_id
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        ) rem ON true
        WHERE pec.eligibility_id = %s
        ORDER BY pec.updated_at DESC NULLS LAST, pec.id DESC
        LIMIT 1
        """,
        (candidate_id,),
    ).fetchone()
    return dict(row) if row else None


def _plan_from_candidate(row: dict[str, Any], *, event_id: str | None, correlation_id: str | None) -> ExitFoundationPlan:
    candidate_id = str(row["eligibility_id"])
    side = _normalize_side(row.get("side"))
    market_id = str(row["market_id"]) if row.get("market_id") else None
    orderbook_id = int(row["orderbook_snapshot_pk"]) if row.get("orderbook_snapshot_pk") is not None else None
    blockers: set[str] = set()
    missing: set[str] = set()
    warnings: set[str] = {"CANDIDATE_SCOPED_EXIT_REFRESH", "PAPER_READY_FALSE"}

    if not market_id:
        missing.add("MISSING_MARKET_ID")
        blockers.add("MISSING_MARKET_ID")
    if not side:
        missing.add("MISSING_SIDE")
        blockers.add("MISSING_SIDE")
    if not row.get("token_id"):
        missing.add("MISSING_TOKEN_ID")
        blockers.add("MISSING_TOKEN_ID")
    if orderbook_id is None or bool(row.get("orderbook_is_stale")) or str(row.get("orderbook_snapshot_status") or "").upper() in {"STALE", "ERROR", "EMPTY", "PARTIAL"}:
        missing.add("MISSING_FRESH_ORDERBOOK")
        blockers.add("MISSING_FRESH_ORDERBOOK")

    risk_decision = str(row.get("risk_evidence_decision") or "").upper()
    if risk_decision == "RISK_BLOCK":
        blockers.add("RISK_BLOCKED")
        if row.get("risk_evidence_blocker"):
            blockers.add(str(row["risk_evidence_blocker"]).upper())
    elif not risk_decision:
        missing.add("MISSING_RISK_EVIDENCE")
        blockers.add("MISSING_RISK_EVIDENCE")

    mid = _maybe_float(row.get("orderbook_mid_price"))
    if mid is None:
        bid = _maybe_float(row.get("orderbook_best_bid"))
        ask = _maybe_float(row.get("orderbook_best_ask"))
        mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
    if mid is None:
        missing.add("MISSING_MID_PRICE")
        blockers.add("MISSING_MID_PRICE")

    spread = _maybe_float(row.get("orderbook_spread"))
    if spread is not None and spread > MAX_SPREAD:
        blockers.add("EXIT_SPREAD_TOO_WIDE")
    liquidity = _maybe_float(row.get("orderbook_liquidity_score"))
    if liquidity is not None and liquidity < MIN_LIQUIDITY_SCORE:
        blockers.add("EXIT_LIQUIDITY_INSUFFICIENT")

    target_exit, stop_loss = _target_stop(side=side, mid=mid)
    if blockers:
        status = "BLOCKED" if "RISK_BLOCKED" in blockers else "INCOMPLETE"
        exit_type = "BLOCKED_NO_ENTRY_EXIT" if "RISK_BLOCKED" in blockers else "LIQUIDITY_PROTECTION_EXIT"
    else:
        status = "COMPLETE"
        exit_type = "BASIC_PROTECTIVE_EXIT"
    paper_exit_ready = status == "COMPLETE"

    return ExitFoundationPlan(
        exit_plan_id=f"exit_candidate_{candidate_id}",
        thesis_id=None,
        risk_decision_id=str(row.get("risk_decision_id") or row.get("risk_evidence_id") or "") or None,
        market_id=market_id,
        side=side,
        status=status,
        exit_type=exit_type,
        target_exit=target_exit,
        stop_loss=stop_loss,
        max_hold_seconds=MAX_HOLD_SECONDS_DEFAULT,
        invalidation_rules=_invalidation_rules(),
        emergency_exit_rules=_emergency_exit_rules(),
        liquidity_exit_check={
            "max_spread": MAX_SPREAD,
            "min_liquidity_score": MIN_LIQUIDITY_SCORE,
            "stale_threshold_seconds": ORDERBOOK_STALE_SECONDS,
            "current_spread": spread,
            "current_liquidity_score": liquidity,
            "orderbook_snapshot_status": row.get("orderbook_snapshot_status"),
            "candidate_id": candidate_id,
            "event_id": event_id,
            "correlation_id": correlation_id,
            "token_id": row.get("token_id"),
        },
        time_exit_check={"max_hold_seconds": MAX_HOLD_SECONDS_DEFAULT, "policy": "time_exit_required_before_any_entry"},
        missing_exit_evidence=sorted(missing),
        blockers=sorted(blockers),
        warnings=sorted(warnings),
        source_risk_status=risk_decision or None,
        source_risk_score=_maybe_float(row.get("risk_evidence_score")),
        orderbook_snapshot_id=orderbook_id,
        paper_intent_allowed=False,
        paper_exit_ready=paper_exit_ready,
        execution_allowed=False,
        generated_by="runtime",
        producer_name="exit_foundation_candidate_scoped",
        is_runtime_generated=True,
        is_dry_run_generated=False,
    )


def _target_stop(*, side: str | None, mid: float | None) -> tuple[float | None, float | None]:
    if side not in {"YES", "NO"} or mid is None:
        return None, None
    if side == "YES":
        return _price(mid + 0.05), _price(mid - 0.03)
    return _price(mid - 0.05), _price(mid + 0.03)


def _price(value: float) -> float:
    return round(max(0.01, min(0.99, value)), 4)


def _mid_price(row: dict[str, Any]) -> float | None:
    mid = _maybe_float(row.get("orderbook_mid_price"))
    if mid is not None:
        return mid
    bid = _maybe_float(row.get("orderbook_best_bid"))
    ask = _maybe_float(row.get("orderbook_best_ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return None


def _normalize_side(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized in {"YES", "NO"}:
        return normalized
    return normalized or None


def _invalidation_rules() -> list[str]:
    return [
        "EMERGENCY_KILL_ACTIVE",
        "LIQUIDITY_BELOW_THRESHOLD",
        "MARKET_LINK_LOST",
        "ORDERBOOK_STALE",
        "RISK_DECISION_CHANGED",
        "SOURCE_DATA_STALE",
        "SPREAD_TOO_WIDE",
        "THESIS_INVALIDATED",
    ]


def _emergency_exit_rules() -> list[str]:
    return [
        "LIQUIDITY_COLLAPSE",
        "MANUAL_KILL",
        "MISSING_PRICE",
        "RISK_STATE_CRITICAL",
        "STALE_ORDERBOOK",
    ]


def _safety_counts(factory: DatabaseConnectionFactory) -> dict[str, int]:
    counts = {"orders": 0, "order_intents": 0, "fills": 0, "positions": 0, "live_actions": 0}
    if not factory.enabled:
        return counts
    with factory.connect() as conn:
        for key, table in {
            "orders": "paper_orders",
            "order_intents": "order_intents",
            "fills": "fills_v2",
            "positions": "positions",
            "live_actions": "live_orders",
        }.items():
            if _table_exists(conn, table):
                counts[key] = _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
    return counts


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


def _missing_count(rows: list[dict[str, Any]], code: str) -> int:
    for row in rows:
        if str(row.get("missing_evidence") or "").upper() == code:
            return _int(row.get("count"))
    return 0


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _empty_summary() -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": "OK",
        "latest_run": None,
        "total_exit_plans": 0,
        "complete_exit_plans": 0,
        "incomplete_exit_plans": 0,
        "blocked_exit_plans": 0,
        "paper_exit_ready_count": 0,
        "paper_intent_allowed_count": 0,
        "execution_allowed_count": 0,
        "missing_market_count": 0,
        "missing_orderbook_count": 0,
        "missing_side_count": 0,
        "missing_risk_approval_count": 0,
        "top_exit_blockers": [],
        "target_exit_count": 0,
        "stop_loss_count": 0,
        "max_hold_seconds_default": MAX_HOLD_SECONDS_DEFAULT,
        "emergency_exit_rules_count": 0,
        "liquidity_exit_check_count": 0,
        "missing_exit_evidence_summary": [],
        "invalidation_rule_summary": [],
        "emergency_exit_summary": [],
        "latest_exit_plans": [],
        "paper_ready": False,
        "orders_created": 0,
        "order_intents_created": 0,
        "fills_created": 0,
        "positions_created": 0,
        "live_actions_created": 0,
        "remaining_blockers": [],
        "analysis_status": "OK",
        "last_updated": datetime.now(UTC).isoformat(),
    }
