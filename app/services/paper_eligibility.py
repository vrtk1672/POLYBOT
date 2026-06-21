from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.paper_eligibility import PaperEligibilityCandidate, PaperEligibilityRun
from app.repositories.paper_eligibility_repository import PaperEligibilityRepository, paper_eligibility_from_row


ORDERBOOK_STALE_STATUSES = {"STALE", "ERROR", "EMPTY", "PARTIAL"}


class PaperEligibilityService:
    """Non-executing Paper Eligibility Gate.

    This service classifies future Paper candidates but intentionally stops before
    Paper intents, order intents, orders, fills, positions, or execution actions.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: PaperEligibilityRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or PaperEligibilityRepository()

    def evaluate_candidates(
        self,
        *,
        limit: int = 100,
        include_blocked: bool = True,
        write_candidates: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"paper_eligibility_{uuid4().hex}"
        safety_before = _safety_counts(self._factory)
        rows: list[dict[str, Any]] = []
        if self._factory.enabled:
            with self._factory.connect() as conn:
                rows = self._repository.list_exit_plan_inputs(conn, limit=limit, include_blocked=include_blocked)

        candidates: list[PaperEligibilityCandidate] = []
        errors: list[str] = []
        for row in rows:
            try:
                candidates.append(_candidate_from_exit_plan(row))
            except Exception as exc:
                errors.append(f"{row.get('exit_plan_id') or 'unknown'}:{type(exc).__name__}:{exc}")

        created = 0
        updated = 0
        if write_candidates and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                for candidate in candidates:
                    _, was_created = self._repository.upsert_candidate(conn, candidate)
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1

        safety_after = _safety_counts(self._factory)
        run = PaperEligibilityRun(
            run_id=run_id,
            status="ERROR" if errors and not candidates else "PARTIAL" if errors else "OK",
            exit_plans_checked=len(rows),
            candidates_created=created,
            candidates_updated=updated,
            eligible_count=len([item for item in candidates if item.status == "ELIGIBLE"]),
            ineligible_count=len([item for item in candidates if item.status == "INELIGIBLE"]),
            blocked_count=len([item for item in candidates if item.status == "BLOCKED"]),
            incomplete_count=len([item for item in candidates if item.status == "INCOMPLETE"]),
            missing_exit_plan_count=len([item for item in candidates if "MISSING_EXIT_PLAN" in item.missing_requirements or "MISSING_EXIT_PLAN" in item.eligibility_blockers]),
            missing_risk_decision_count=len([item for item in candidates if "MISSING_RISK_DECISION" in item.missing_requirements or "MISSING_RISK_DECISION" in item.eligibility_blockers]),
            missing_thesis_count=len([item for item in candidates if "MISSING_THESIS" in item.missing_requirements or "MISSING_THESIS" in item.eligibility_blockers]),
            missing_market_count=len([item for item in candidates if "MISSING_MARKET_ID" in item.missing_requirements or "MISSING_MARKET_ID" in item.eligibility_blockers]),
            missing_orderbook_count=len([item for item in candidates if "MISSING_FRESH_ORDERBOOK" in item.missing_requirements or "MISSING_FRESH_ORDERBOOK" in item.eligibility_blockers]),
            missing_binding_count=len([item for item in candidates if "MISSING_SIGNAL_MARKET_BINDING" in item.missing_requirements or "MISSING_SIGNAL_MARKET_BINDING" in item.eligibility_blockers]),
            missing_lineage_count=len([item for item in candidates if "WEAK_LINEAGE_OR_PROVENANCE" in item.missing_requirements or "WEAK_LINEAGE_OR_PROVENANCE" in item.eligibility_blockers]),
            dry_run_blocked_count=len([item for item in candidates if "DRY_RUN_EVIDENCE" in item.missing_requirements or "DRY_RUN_EVIDENCE" in item.eligibility_blockers]),
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            fills_created=max(0, safety_after["fills"] - safety_before["fills"]),
            positions_created=max(0, safety_after["positions"] - safety_before["positions"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            candidates=candidates,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary="; ".join(errors) if errors else None,
        )
        if write_candidates and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
        return run.to_api_dict()

    def list_recent(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "OK", "count": 0, "candidates": []}
        with self._factory.connect() as conn:
            rows = self._repository.list_candidates(conn, limit=limit, status=status, market_id=market_id)
        candidates = [paper_eligibility_from_row(row).to_api_dict() for row in rows]
        return {"mock_data": False, "status": "OK", "count": len(candidates), "candidates": candidates}

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "paper_eligibility_candidates"):
                return _empty_summary()
            summary = self._repository.summary(conn, limit=limit)
        latest_run = summary.get("latest_run") or {}
        missing_summary = summary.get("missing_requirement_summary", [])
        return {
            "mock_data": False,
            "status": "OK",
            "latest_run": _json_safe(latest_run) if latest_run else None,
            "total_candidates": _int(summary.get("total_candidates")),
            "eligible_count": _int(summary.get("eligible_count")),
            "ineligible_count": _int(summary.get("ineligible_count")),
            "blocked_count": _int(summary.get("blocked_count")),
            "incomplete_count": _int(summary.get("incomplete_count")),
            "paper_intent_allowed_count": _int(summary.get("paper_intent_allowed_count")),
            "execution_allowed_count": _int(summary.get("execution_allowed_count")),
            "missing_exit_plan_count": _missing_count(missing_summary, "MISSING_EXIT_PLAN"),
            "missing_risk_decision_count": _missing_count(missing_summary, "MISSING_RISK_DECISION"),
            "missing_thesis_count": _missing_count(missing_summary, "MISSING_THESIS"),
            "missing_market_count": _missing_count(missing_summary, "MISSING_MARKET_ID"),
            "missing_orderbook_count": _missing_count(missing_summary, "MISSING_FRESH_ORDERBOOK"),
            "missing_binding_count": _missing_count(missing_summary, "MISSING_SIGNAL_MARKET_BINDING"),
            "missing_lineage_count": _missing_count(missing_summary, "WEAK_LINEAGE_OR_PROVENANCE"),
            "dry_run_blocked_count": _missing_count(missing_summary, "DRY_RUN_EVIDENCE"),
            "top_eligibility_blockers": [_json_safe(row) for row in summary.get("top_eligibility_blockers", [])],
            "missing_requirement_summary": [_json_safe(row) for row in missing_summary],
            "latest_candidates": [_json_safe(paper_eligibility_from_row(row).to_api_dict()) for row in summary.get("latest_candidates", [])],
            "paper_ready": False,
            "orders_created": _int(latest_run.get("orders_created")) if latest_run else 0,
            "order_intents_created": _int(latest_run.get("order_intents_created")) if latest_run else 0,
            "fills_created": _int(latest_run.get("fills_created")) if latest_run else 0,
            "positions_created": _int(latest_run.get("positions_created")) if latest_run else 0,
            "live_actions_created": _int(latest_run.get("live_actions_created")) if latest_run else 0,
            "remaining_blockers": [],
            "analysis_status": "OK",
            "last_updated": datetime.now(UTC).isoformat(),
        }


def _candidate_from_exit_plan(row: dict[str, Any]) -> PaperEligibilityCandidate:
    exit_plan_id = row.get("exit_plan_id")
    risk_decision_id = row.get("risk_decision_id")
    thesis_id = row.get("thesis_id")
    market_id = row.get("exit_market_id") or row.get("risk_market_id") or row.get("thesis_market_id")
    side = row.get("exit_side") or row.get("thesis_side")
    orderbook_snapshot_id = row.get("exit_orderbook_snapshot_id") or row.get("risk_orderbook_snapshot_id") or row.get("thesis_orderbook_snapshot_id")
    brain_output_ids = _list(row.get("source_brain_output_ids"))
    signal_ids = _list(row.get("source_signal_ids"))

    missing: set[str] = set()
    blockers: set[str] = set()
    if not exit_plan_id:
        missing.add("MISSING_EXIT_PLAN")
        blockers.add("MISSING_EXIT_PLAN")
    if str(row.get("exit_status") or "").upper() == "BLOCKED":
        blockers.add("EXIT_NOT_READY")
    if str(row.get("exit_status") or "").upper() == "INCOMPLETE":
        missing.add("EXIT_NOT_READY")
        blockers.add("EXIT_NOT_READY")
    if not bool(row.get("paper_exit_ready")):
        missing.add("EXIT_NOT_READY")
        blockers.add("EXIT_NOT_READY")
    if not risk_decision_id:
        missing.add("MISSING_RISK_DECISION")
        blockers.add("MISSING_RISK_DECISION")
    if not bool(row.get("risk_approved")):
        missing.add("RISK_NOT_APPROVED")
        blockers.add("RISK_NOT_APPROVED")
    if not thesis_id:
        missing.add("MISSING_THESIS")
        blockers.add("MISSING_THESIS")
    if str(row.get("thesis_status") or "").upper() != "COMPLETE":
        missing.add("THESIS_NOT_COMPLETE")
        blockers.add("THESIS_NOT_COMPLETE")
    if not market_id:
        missing.add("MISSING_MARKET_ID")
        blockers.add("MISSING_MARKET_ID")
    if not side:
        missing.add("MISSING_SIDE")
        blockers.add("MISSING_SIDE")
    if orderbook_snapshot_id is None or bool(row.get("orderbook_is_stale")) or str(row.get("orderbook_snapshot_status") or "").upper() in ORDERBOOK_STALE_STATUSES:
        missing.add("MISSING_FRESH_ORDERBOOK")
        blockers.add("MISSING_FRESH_ORDERBOOK")
    link_confidence = _maybe_float(row.get("link_confidence"))
    if not signal_ids or _int(row.get("link_count")) <= 0 or link_confidence is None:
        missing.add("MISSING_SIGNAL_MARKET_BINDING")
        blockers.add("MISSING_SIGNAL_MARKET_BINDING")
    lineage_trusted = bool(signal_ids and brain_output_ids and row.get("coordinator_decision_id"))
    if not lineage_trusted:
        missing.add("WEAK_LINEAGE_OR_PROVENANCE")
        blockers.add("WEAK_LINEAGE_OR_PROVENANCE")
    not_dry_run = bool(row.get("risk_runtime_generated")) and not bool(row.get("risk_dry_run_generated")) and bool(row.get("thesis_runtime_generated")) and not bool(row.get("thesis_dry_run_generated"))
    if not not_dry_run:
        missing.add("DRY_RUN_EVIDENCE")
        blockers.add("DRY_RUN_EVIDENCE")
    if bool(row.get("coordinator_execution_allowed")):
        blockers.add("COORDINATOR_EXECUTION_ALLOWED_UNSAFE")
    exit_blockers = {str(item).upper() for item in _list(row.get("exit_blockers"))}
    if "RISK_BLOCKED" in exit_blockers or "RISK_REJECTED" in exit_blockers:
        blockers.update(exit_blockers & {"RISK_BLOCKED", "RISK_REJECTED"})

    status = "ELIGIBLE"
    if blockers:
        status = "BLOCKED"
    elif missing:
        status = "INCOMPLETE"

    if status == "ELIGIBLE":
        score = 1.0
    else:
        score = 0.0

    return PaperEligibilityCandidate(
        eligibility_id=f"eligibility_{exit_plan_id or risk_decision_id or uuid4().hex}",
        thesis_id=str(thesis_id) if thesis_id else None,
        risk_decision_id=str(risk_decision_id) if risk_decision_id else None,
        exit_plan_id=str(exit_plan_id) if exit_plan_id else None,
        coordinator_decision_id=str(row["coordinator_decision_id"]) if row.get("coordinator_decision_id") else None,
        brain_output_ids=brain_output_ids,
        signal_ids=signal_ids,
        market_id=str(market_id) if market_id else None,
        side=str(side).upper() if side else None,
        status=status,
        eligibility_score=score,
        eligibility_blockers=sorted(blockers),
        missing_requirements=sorted(missing),
        evidence={
            "exit_status": row.get("exit_status"),
            "risk_decision": row.get("risk_decision"),
            "risk_status": row.get("risk_status"),
            "thesis_status": row.get("thesis_status"),
            "orderbook_snapshot_status": row.get("orderbook_snapshot_status"),
            "orderbook_best_bid": _maybe_float(row.get("orderbook_best_bid")),
            "orderbook_best_ask": _maybe_float(row.get("orderbook_best_ask")),
            "orderbook_mid_price": _maybe_float(row.get("orderbook_mid_price")),
            "orderbook_spread": _maybe_float(row.get("orderbook_spread")),
            "orderbook_liquidity_score": _maybe_float(row.get("orderbook_liquidity_score")),
            "link_count": _int(row.get("link_count")),
        },
        orderbook_snapshot_id=int(orderbook_snapshot_id) if orderbook_snapshot_id is not None else None,
        link_confidence=link_confidence,
        lineage_trusted=lineage_trusted,
        risk_approved=bool(row.get("risk_approved")),
        exit_ready=bool(row.get("paper_exit_ready")),
        not_dry_run=not_dry_run,
        paper_intent_allowed=False,
        execution_allowed=False,
        generated_by="runtime",
        producer_name="paper_eligibility_gate",
        is_runtime_generated=True,
        is_dry_run_generated=False,
    )


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
        if str(row.get("missing_requirement") or "").upper() == code:
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
        "total_candidates": 0,
        "eligible_count": 0,
        "ineligible_count": 0,
        "blocked_count": 0,
        "incomplete_count": 0,
        "paper_intent_allowed_count": 0,
        "execution_allowed_count": 0,
        "missing_exit_plan_count": 0,
        "missing_risk_decision_count": 0,
        "missing_thesis_count": 0,
        "missing_market_count": 0,
        "missing_orderbook_count": 0,
        "missing_binding_count": 0,
        "missing_lineage_count": 0,
        "dry_run_blocked_count": 0,
        "top_eligibility_blockers": [],
        "missing_requirement_summary": [],
        "latest_candidates": [],
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
