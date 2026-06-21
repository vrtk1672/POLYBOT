from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.db.connection import DatabaseConnectionFactory
from app.services.source_event_memory import SourceEventMemoryService


class SourceEventMemoryControlService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._service = SourceEventMemoryService(connection_factory=self._factory)

    def get_summary(self, *, limit: int = 10) -> dict[str, Any]:
        return _envelope(self._service.summary(limit=limit))

    def refresh(self, *, force: bool = False, window_hours: int = 72, limit: int = 500) -> dict[str, Any]:
        result = self._service.refresh_events(force=force, window_hours=window_hours, max_events=limit)
        payload = self._service.summary(limit=10)
        payload["latest_refresh_action"] = result
        return _envelope(payload)

    def recall(self, *, source_event_id: str) -> dict[str, Any]:
        result = self._service.recall(source_event_id=source_event_id)
        payload = {
            "status": "REAL" if result.get("source_event") else "MISSING",
            "source": "source_event_memory recall",
            "last_updated": datetime.now(UTC).isoformat(),
            "freshness_state": "FRESH" if result.get("source_event") else "MISSING",
            "readiness_state": "READY" if result.get("source_event") else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if result.get("source_event") else "UNKNOWN",
            "result": result,
            "warnings": [] if result.get("source_event") else ["No source event memory row matched the requested ID."],
            "errors": [],
        }
        return _envelope(payload)

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        result = self._service.by_market(market_id=market_id, limit=limit)
        payload = {
            "status": "REAL",
            "source": "source_event_memory by-market recall",
            "last_updated": datetime.now(UTC).isoformat(),
            "freshness_state": "FRESH",
            "readiness_state": "READY",
            "truth_state": "ACTIVE_FRESH",
            "result": result,
            "warnings": [],
            "errors": [],
        }
        return _envelope(payload)

    def linker_diagnostics(self) -> dict[str, Any]:
        result = self._service.linker_diagnostics()
        payload = {
            "status": "REAL" if result.get("status") == "REAL" else "PARTIAL",
            "source": "source_event_memory linker diagnostics",
            "last_updated": datetime.now(UTC).isoformat(),
            "freshness_state": "FRESH",
            "readiness_state": "READY",
            "truth_state": "ACTIVE_FRESH",
            "result": result,
            "warnings": [],
            "errors": [],
        }
        return _envelope(payload)


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status_value = payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL"
    envelope = truth_envelope(
        status=ControlCenterStatus(status_value),
        source=str(payload.get("source") or "source_event_memory"),
        truth_state=payload.get("truth_state") if payload.get("truth_state") in {item.value for item in ControlCenterTruthState} else ControlCenterTruthState.UNKNOWN,
        data=payload,
        last_updated=payload.get("last_updated"),
        stale_after_seconds=3600,
        freshness_state=ControlCenterFreshnessState(payload.get("freshness_state") if payload.get("freshness_state") in {item.value for item in ControlCenterFreshnessState} else "MISSING"),
        runtime_state=ControlCenterRuntimeState.REGISTERED if status_value in {"REAL", "PARTIAL"} else ControlCenterRuntimeState.UNKNOWN,
        readiness_state=ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {item.value for item in ControlCenterReadinessState} else "UNKNOWN"),
        warnings=payload.get("warnings") or [],
        errors=payload.get("errors") or [],
    ).to_dict()
    return {**envelope, **payload, "data": payload}
