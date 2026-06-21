from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.signal_processing import SignalProcessingState, signal_processing_from_row
from app.repositories.signal_processing_repository import SignalProcessingRepository
from app.services.signal_quality import SignalQualityService


class SignalProcessingService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: SignalProcessingRepository | None = None,
        quality_service: SignalQualityService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or SignalProcessingRepository()
        self._quality_service = quality_service or SignalQualityService(connection_factory=self._factory)

    def evaluate_signal_processing(self, signal_id: str, *, refresh_quality: bool = False) -> dict[str, Any] | None:
        if refresh_quality:
            self._quality_service.evaluate_signal_quality(signal_id)
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            context = self._repository.get_signal_processing_context(conn, signal_id)
            if not context:
                return None
            state = evaluate_processing_context(context)
            row = self._repository.upsert_state(conn, state)
        return _state_response(row, [])

    def evaluate_recent_signals(self, *, limit: int = 100, refresh_quality: bool = False) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "OK", "mock_data": False, "evaluated": 0, "created_or_updated": 0, "summary": _empty_summary()}
        if refresh_quality:
            self._quality_service.evaluate_recent_signals(limit=limit)
        with self._factory.connect() as conn, conn.transaction():
            signal_ids = self._repository.list_recent_signal_ids(conn, limit=limit)
            updated = 0
            for signal_id in signal_ids:
                context = self._repository.get_signal_processing_context(conn, signal_id)
                if not context:
                    continue
                state = evaluate_processing_context(context)
                self._repository.upsert_state(conn, state)
                updated += 1
            summary = self._repository.summary(conn, limit=20)
        return {
            "status": "OK" if updated == len(signal_ids) else "DEGRADED",
            "mock_data": False,
            "evaluated": len(signal_ids),
            "created_or_updated": updated,
            "summary": _summary_response(summary),
        }

    def get_signal_processing(self, signal_id: str, *, include_history: bool = True) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_state(conn, signal_id)
            history = self._repository.list_history(conn, signal_id) if row and include_history else []
        return _state_response(row, history) if row else None

    def list_signal_processing(
        self,
        *,
        limit: int = 50,
        state: str | None = None,
        gate_status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_states(conn, limit=limit, state=state, gate_status=gate_status)
        return [_state_response(row, []) for row in rows]

    def get_signal_processing_summary(self, *, limit: int = 20) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_summary()
        with self._factory.connect() as conn:
            summary = self._repository.summary(conn, limit=limit)
        return _summary_response(summary)

    def mark_ignored(self, signal_id: str, *, ignored_reason: str) -> dict[str, Any] | None:
        if not ignored_reason.strip():
            raise ValueError("ignored_reason is required")
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            context = self._repository.get_signal_processing_context(conn, signal_id)
            if not context:
                return None
            state = evaluate_processing_context(context)
            state.processing_state = "IGNORED"
            state.gate_status = "BLOCKED"
            state.ignored_reason = ignored_reason.strip()
            state.gate_blockers = sorted(set([*state.gate_blockers, "ignored"]))
            row = self._repository.upsert_state(conn, state, actor="signal_processing_ignore")
        return _state_response(row, [])

    def mark_error(self, signal_id: str, *, error_reason: str) -> dict[str, Any] | None:
        if not error_reason.strip():
            raise ValueError("error_reason is required")
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            context = self._repository.get_signal_processing_context(conn, signal_id)
            if not context:
                return None
            state = evaluate_processing_context(context)
            state.processing_state = "ERROR"
            state.gate_status = "ERROR"
            state.error_reason = error_reason.strip()
            state.gate_blockers = sorted(set([*state.gate_blockers, "processing_error"]))
            row = self._repository.upsert_state(conn, state, actor="signal_processing_error")
        return _state_response(row, [])


def evaluate_processing_context(row: dict[str, Any]) -> SignalProcessingState:
    has_quality = row.get("quality_evaluation_id") is not None
    linked_to_market = bool(row.get("linked_to_market")) or bool(row.get("quality_linked_to_market"))
    linked_to_position = bool(row.get("linked_to_position")) or bool(row.get("quality_linked_to_position"))
    used_by_brain = bool(row.get("used_by_brain_output")) or bool(row.get("quality_used_by_brain_output"))
    used_by_coord = bool(row.get("used_by_coordinator")) or bool(row.get("quality_used_by_coordinator"))
    is_stale = bool(row.get("is_stale")) if has_quality else False
    can_feed_brain = bool(row.get("can_feed_brain")) if has_quality and not is_stale else False
    can_feed_paper = bool(row.get("can_feed_paper")) if has_quality and not is_stale else False
    missing = list(row.get("missing_fields_json") or []) if has_quality else []

    processing_state = "NEW"
    gate_status = "NOT_EVALUATED"
    if linked_to_market or linked_to_position:
        processing_state = "LINKED"
    if has_quality:
        processing_state = "QUALITY_CHECKED"
        gate_status = _gate_status(row, missing)
    if is_stale:
        processing_state = "STALE"
        gate_status = "STALE"
        can_feed_brain = False
        can_feed_paper = False
    elif used_by_coord:
        processing_state = "COORDINATOR_USED"
    elif used_by_brain:
        processing_state = "BRAIN_USED"

    gate_blockers = _gate_blockers(row, missing, has_quality=has_quality)
    rejection_reason = None
    if gate_status == "BLOCKED":
        rejection_reason = f"Quality gate blocked by: {', '.join(gate_blockers) or 'missing quality requirements'}"

    return SignalProcessingState(
        signal_id=str(row["signal_id"]),
        processing_state=processing_state,
        quality_evaluation_id=row.get("quality_evaluation_id"),
        quality_score=float(row["quality_score"]) if row.get("quality_score") is not None else None,
        quality_status=row.get("quality_status"),
        gate_status=gate_status,
        gate_blockers=gate_blockers,
        missing_requirements=missing,
        linked_to_market=linked_to_market,
        linked_to_position=linked_to_position,
        used_by_brain_output=used_by_brain,
        used_by_coordinator=used_by_coord,
        is_dry_run_generated=bool(row.get("is_dry_run_generated")),
        is_runtime_generated=bool(row.get("is_runtime_generated")),
        is_stale=is_stale,
        can_feed_brain=can_feed_brain,
        can_feed_paper=can_feed_paper,
        rejection_reason=rejection_reason,
        evaluated_at=row.get("evaluated_at"),
    )


def _gate_status(row: dict[str, Any], missing: list[str]) -> str:
    quality_status = str(row.get("quality_status") or "").upper()
    if quality_status == "ERROR":
        return "ERROR"
    if bool(row.get("is_stale")) or quality_status == "STALE":
        return "STALE"
    if bool(row.get("can_feed_paper")):
        return "PAPER_ELIGIBLE_INFORMATIONAL_ONLY"
    if bool(row.get("can_feed_brain")):
        return "BRAIN_ELIGIBLE"
    if quality_status in {"BLOCKED", "UNBOUND", "WEAK"}:
        return "BLOCKED"
    return "PAPER_BLOCKED" if missing else "BLOCKED"


def _gate_blockers(row: dict[str, Any], missing: list[str], *, has_quality: bool) -> list[str]:
    blockers = list(missing)
    if not has_quality:
        blockers.append("quality_not_evaluated")
    if bool(row.get("is_stale")):
        blockers.append("stale_signal")
    if bool(row.get("is_dry_run_generated")):
        blockers.append("dry_run_generated")
    if not bool(row.get("can_feed_paper")):
        blockers.append("paper_quality_gate")
    return sorted(set(blockers))


def _summary_response(summary: dict[str, Any]) -> dict[str, Any]:
    total = int(summary.get("total") or 0)
    status = "EMPTY"
    if total:
        status = "DEGRADED" if int(summary.get("stale_count") or 0) or int(summary.get("unprocessed_count") or 0) or int(summary.get("paper_eligible_informational_count") or 0) == 0 else "OK"
    return {
        "status": status,
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "last_updated": _json_safe(summary.get("last_updated")),
        "total": total,
        "by_state": [_json_safe(row) for row in summary.get("by_state", [])],
        "by_gate_status": [_json_safe(row) for row in summary.get("by_gate_status", [])],
        "unprocessed_count": int(summary.get("unprocessed_count") or 0),
        "quality_checked_count": int(summary.get("quality_checked_count") or 0),
        "brain_used_count": int(summary.get("brain_used_count") or 0),
        "coordinator_used_count": int(summary.get("coordinator_used_count") or 0),
        "stale_count": int(summary.get("stale_count") or 0),
        "rejected_count": int(summary.get("rejected_count") or 0),
        "error_count": int(summary.get("error_count") or 0),
        "brain_eligible_count": int(summary.get("brain_eligible_count") or 0),
        "paper_eligible_informational_count": int(summary.get("paper_eligible_informational_count") or 0),
        "top_gate_blockers": [_json_safe(row) for row in summary.get("top_gate_blockers", [])],
        "latest_states": [_state_response(row, []) for row in summary.get("latest_states", [])],
        "paper_ready": False,
    }


def _state_response(row: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    state = signal_processing_from_row(dict(row)).to_api_dict()
    state["blocked_by"] = state.get("gate_blockers", [])
    state["history"] = [_json_safe(item) for item in history]
    return state


def _empty_summary() -> dict[str, Any]:
    return {
        "status": "OK",
        "mock_data": False,
        "updated_at": datetime.now(UTC).isoformat(),
        "last_updated": None,
        "total": 0,
        "by_state": [],
        "by_gate_status": [],
        "unprocessed_count": 0,
        "quality_checked_count": 0,
        "brain_used_count": 0,
        "coordinator_used_count": 0,
        "stale_count": 0,
        "rejected_count": 0,
        "error_count": 0,
        "brain_eligible_count": 0,
        "paper_eligible_informational_count": 0,
        "top_gate_blockers": [],
        "latest_states": [],
        "paper_ready": False,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value
