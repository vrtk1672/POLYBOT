from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.risk_core import RiskCoreRun, RiskDecision
from app.repositories.risk_core_repository import RiskCoreRepository, risk_decision_from_row


MAX_POSITION_SIZE_DEFAULT = 10.0
MAX_LOSS_DEFAULT = 5.0
CONFIDENCE_THRESHOLD = 0.60
MAX_SPREAD = 0.08
MIN_LIQUIDITY_SCORE = 0.25


class RiskCoreService:
    """Thesis-derived, non-executing Risk Core foundation."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: RiskCoreRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or RiskCoreRepository()

    def evaluate_risk(
        self,
        *,
        limit: int = 100,
        include_blocked: bool = True,
        write_decisions: bool = True,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = f"risk_core_{uuid4().hex}"
        safety_before = _safety_counts(self._factory)
        rows: list[dict[str, Any]] = []
        if self._factory.enabled:
            with self._factory.connect() as conn:
                rows = self._repository.list_runtime_thesis_profiles(conn, limit=limit, include_blocked=include_blocked)

        decisions: list[RiskDecision] = []
        errors: list[str] = []
        for row in rows:
            try:
                decisions.append(_decision_from_thesis(row))
            except Exception as exc:
                errors.append(f"{row.get('thesis_id') or 'unknown'}:{type(exc).__name__}:{exc}")

        created = 0
        updated = 0
        if write_decisions and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                for decision in decisions:
                    _, was_created = self._repository.upsert_decision(conn, decision)
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1

        safety_after = _safety_counts(self._factory)
        run = RiskCoreRun(
            run_id=run_id,
            status="ERROR" if errors and not decisions else "PARTIAL" if errors else "OK",
            thesis_profiles_checked=len(rows),
            risk_decisions_created=created,
            risk_decisions_updated=updated,
            approved_count=len([item for item in decisions if item.decision == "APPROVE"]),
            rejected_count=len([item for item in decisions if item.decision == "REJECT"]),
            blocked_count=len([item for item in decisions if item.decision == "BLOCK"]),
            warning_count=len([item for item in decisions if item.decision == "WARN_ONLY"]),
            max_position_size_default=MAX_POSITION_SIZE_DEFAULT,
            max_loss_default=MAX_LOSS_DEFAULT,
            confidence_threshold=CONFIDENCE_THRESHOLD,
            paper_ready_before=False,
            paper_ready_after=False,
            orders_created=max(0, safety_after["orders"] - safety_before["orders"]),
            order_intents_created=max(0, safety_after["order_intents"] - safety_before["order_intents"]),
            fills_created=max(0, safety_after["fills"] - safety_before["fills"]),
            positions_created=max(0, safety_after["positions"] - safety_before["positions"]),
            live_actions_created=max(0, safety_after["live_actions"] - safety_before["live_actions"]),
            decisions=decisions,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error_summary="; ".join(errors) if errors else None,
        )
        if write_decisions and self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.record_run(conn, run)
        return run.to_api_dict()

    def list_recent(
        self,
        *,
        limit: int = 50,
        decision: str | None = None,
        market_id: str | None = None,
        thesis_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "OK", "count": 0, "risk_decisions": []}
        with self._factory.connect() as conn:
            rows = self._repository.list_decisions(conn, limit=limit, decision=decision, market_id=market_id, thesis_id=thesis_id)
        decisions = [risk_decision_from_row(row).to_api_dict() for row in rows]
        return {"mock_data": False, "status": "OK", "count": len(decisions), "risk_decisions": decisions}

    def get_dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            if not _table_exists(conn, "risk_decisions"):
                return _empty_summary()
            summary = self._repository.summary(conn, limit=limit)
        latest_run = summary.get("latest_run") or {}
        return {
            "mock_data": False,
            "status": "OK",
            "latest_run": _json_safe(latest_run) if latest_run else None,
            "total_risk_decisions": _int(summary.get("total_risk_decisions")),
            "approved_count": _int(summary.get("approved_count")),
            "rejected_count": _int(summary.get("rejected_count")),
            "blocked_count": _int(summary.get("blocked_count")),
            "warning_count": _int(summary.get("warning_count")),
            "avg_risk_score": _float(summary.get("avg_risk_score")),
            "max_position_size_default": MAX_POSITION_SIZE_DEFAULT,
            "max_loss_default": MAX_LOSS_DEFAULT,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "top_risk_blockers": [_json_safe(row) for row in summary.get("top_risk_blockers", [])],
            "missing_data_risk_count": _int(summary.get("missing_data_risk_count")),
            "spread_risk_count": _int(summary.get("spread_risk_count")),
            "liquidity_risk_count": _int(summary.get("liquidity_risk_count")),
            "confidence_risk_count": _int(summary.get("confidence_risk_count")),
            "paper_candidate_allowed_count": _int(summary.get("paper_candidate_allowed_count")),
            "risk_approved_count": _int(summary.get("risk_approved_count")),
            "execution_allowed_count": _int(summary.get("execution_allowed_count")),
            "latest_risk_decisions": [_json_safe(risk_decision_from_row(row).to_api_dict()) for row in summary.get("latest_risk_decisions", [])],
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


def _decision_from_thesis(row: dict[str, Any]) -> RiskDecision:
    thesis_id = str(row["thesis_id"])
    status = str(row.get("status") or "ERROR").upper()
    missing = {str(item).upper() for item in _list(row.get("missing_evidence"))}
    risk_notes = {str(item).upper() for item in _list(row.get("risk_notes"))}
    blockers: set[str] = set()
    warnings: set[str] = {"EXIT_FOUNDATION_MISSING", "DAILY_EXPOSURE_PLACEHOLDER_ONLY"}
    risk_reasons: set[str] = set()

    if status == "BLOCKED":
        blockers.add("THESIS_BLOCKED")
    if status == "INCOMPLETE":
        blockers.add("THESIS_INCOMPLETE")
    if status == "WEAK":
        blockers.add("THESIS_WEAK")
    if not row.get("market_id"):
        blockers.add("MISSING_MARKET_ID")
    if row.get("orderbook_snapshot_id") is None or bool(row.get("orderbook_is_stale")) or str(row.get("orderbook_snapshot_status") or "").upper() in {"STALE", "ERROR", "EMPTY", "PARTIAL"}:
        blockers.add("MISSING_FRESH_ORDERBOOK")
    if "MISSING_SIGNAL_MARKET_BINDING" in missing or (row.get("source_signal_ids") and not row.get("linked_signal_id")):
        blockers.add("MISSING_SIGNAL_MARKET_BINDING")
    if "WEAK_LINEAGE_OR_PROVENANCE" in missing:
        blockers.add("WEAK_LINEAGE_OR_PROVENANCE")
    blockers.update(missing)

    confidence = _clamp(row.get("confidence"))
    if confidence < CONFIDENCE_THRESHOLD:
        blockers.add("CONFIDENCE_TOO_LOW")
    spread = _maybe_float(row.get("orderbook_spread"))
    if spread is not None and spread > MAX_SPREAD:
        blockers.add("SPREAD_TOO_WIDE")
    liquidity = _maybe_float(row.get("orderbook_liquidity_score"))
    if liquidity is not None and liquidity < MIN_LIQUIDITY_SCORE:
        blockers.add("LIQUIDITY_TOO_LOW")
    if "NO_EXIT_FOUNDATION" in risk_notes:
        warnings.add("NO_EXIT_FOUNDATION")

    missing_data_score = 1.0 if blockers & {
        "MISSING_MARKET_ID",
        "MISSING_FRESH_ORDERBOOK",
        "MISSING_SIGNAL_MARKET_BINDING",
        "WEAK_LINEAGE_OR_PROVENANCE",
    } else 0.0
    spread_score = 1.0 if spread is None and "MISSING_FRESH_ORDERBOOK" in blockers else _clamp((spread or 0.0) / MAX_SPREAD)
    liquidity_score = 1.0 if liquidity is None and "MISSING_FRESH_ORDERBOOK" in blockers else _clamp(1.0 - (liquidity or 0.0))
    confidence_score = _clamp((CONFIDENCE_THRESHOLD - confidence) / CONFIDENCE_THRESHOLD) if confidence < CONFIDENCE_THRESHOLD else 0.0
    market_score = 1.0 if status == "BLOCKED" else 0.75 if status in {"INCOMPLETE", "WEAK", "ERROR"} else 0.2
    daily_exposure_score = 0.0
    risk_score = _clamp(max(missing_data_score, spread_score, liquidity_score, confidence_score, market_score, daily_exposure_score))

    if blockers:
        decision = "BLOCK"
        risk_status = "BLOCKED"
        risk_approved = False
    elif risk_score >= 0.85:
        decision = "REJECT"
        risk_status = "CRITICAL"
        risk_approved = False
    elif risk_score >= 0.65:
        decision = "REJECT"
        risk_status = "HIGH"
        risk_approved = False
    else:
        decision = "APPROVE"
        risk_status = "LOW" if risk_score < 0.35 else "MEDIUM"
        risk_approved = True
        warnings.add("RISK_LAYER_APPROVAL_NOT_PAPER_ELIGIBILITY")

    risk_reasons.update(blockers or warnings)
    return RiskDecision(
        risk_decision_id=f"risk_{thesis_id}",
        thesis_id=thesis_id,
        market_id=str(row["market_id"]) if row.get("market_id") else None,
        decision=decision,
        risk_status=risk_status,
        risk_score=risk_score,
        confidence=confidence,
        max_position_size=MAX_POSITION_SIZE_DEFAULT,
        max_loss=MAX_LOSS_DEFAULT,
        market_risk_score=market_score,
        liquidity_risk_score=liquidity_score,
        spread_risk_score=spread_score,
        missing_data_risk_score=missing_data_score,
        confidence_risk_score=confidence_score,
        daily_exposure_risk_score=daily_exposure_score,
        risk_reasons=sorted(risk_reasons),
        blockers=sorted(blockers),
        warnings=sorted(warnings),
        required_missing_evidence=sorted(blockers & {
            "MISSING_MARKET_ID",
            "MISSING_FRESH_ORDERBOOK",
            "MISSING_SIGNAL_MARKET_BINDING",
            "WEAK_LINEAGE_OR_PROVENANCE",
            "CONFIDENCE_TOO_LOW",
        }),
        source_thesis_status=status,
        orderbook_snapshot_id=int(row["orderbook_snapshot_id"]) if row.get("orderbook_snapshot_id") is not None else None,
        paper_candidate_allowed=False,
        execution_allowed=False,
        risk_approved=risk_approved,
        exit_required=True,
        generated_by="runtime",
        producer_name="risk_core",
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
    return [str(value)]


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: Any) -> float:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(1.0, numeric))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


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
        "total_risk_decisions": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "blocked_count": 0,
        "warning_count": 0,
        "avg_risk_score": 0.0,
        "max_position_size_default": MAX_POSITION_SIZE_DEFAULT,
        "max_loss_default": MAX_LOSS_DEFAULT,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "top_risk_blockers": [],
        "missing_data_risk_count": 0,
        "spread_risk_count": 0,
        "liquidity_risk_count": 0,
        "confidence_risk_count": 0,
        "paper_candidate_allowed_count": 0,
        "risk_approved_count": 0,
        "execution_allowed_count": 0,
        "latest_risk_decisions": [],
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
