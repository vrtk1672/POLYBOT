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
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService


class TargetedMarketRevalidationControlService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._service = TargetedMarketRevalidationService(connection_factory=self._factory)

    def get_summary(self, *, limit: int = 10) -> dict[str, Any]:
        return _envelope(self._service.summary(limit=limit))

    def refresh(self, *, limit: int = 50, force: bool = False) -> dict[str, Any]:
        result = self._service.refresh(limit=limit, force=force)
        payload = self._service.summary(limit=10)
        payload["latest_refresh_action"] = result
        return _envelope(payload)

    def by_market(self, *, market_id: str, limit: int = 20) -> dict[str, Any]:
        result = self._service.by_market(market_id=market_id, limit=limit)
        payload = {
            "status": "REAL" if result.get("results") else "MISSING",
            "source": "targeted_market_revalidation by-market",
            "last_updated": datetime.now(UTC).isoformat(),
            "freshness_state": "FRESH" if result.get("results") else "MISSING",
            "readiness_state": "READY" if result.get("results") else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if result.get("results") else "UNKNOWN",
            "result": result,
            "warnings": [] if result.get("results") else ["No targeted revalidation rows matched this market."],
            "errors": [],
        }
        return _envelope(payload)

    def by_event(self, *, source_event_id: str, limit: int = 50) -> dict[str, Any]:
        result = self._service.by_event(source_event_id=source_event_id, limit=limit)
        payload = {
            "status": "REAL" if result.get("results") else "MISSING",
            "source": "targeted_market_revalidation by-event",
            "last_updated": datetime.now(UTC).isoformat(),
            "freshness_state": "FRESH" if result.get("results") else "MISSING",
            "readiness_state": "READY" if result.get("results") else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if result.get("results") else "UNKNOWN",
            "result": result,
            "warnings": [] if result.get("results") else ["No targeted revalidation rows matched this event."],
            "errors": [],
        }
        return _envelope(payload)


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status_value = payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL"
    envelope = truth_envelope(
        status=ControlCenterStatus(status_value),
        source=str(payload.get("source") or "targeted_market_revalidation"),
        truth_state=payload.get("truth_state") if payload.get("truth_state") in {item.value for item in ControlCenterTruthState} else ControlCenterTruthState.UNKNOWN,
        data=payload,
        last_updated=payload.get("last_updated"),
        stale_after_seconds=900,
        freshness_state=ControlCenterFreshnessState(payload.get("freshness_state") if payload.get("freshness_state") in {item.value for item in ControlCenterFreshnessState} else "MISSING"),
        runtime_state=ControlCenterRuntimeState.REGISTERED if status_value in {"REAL", "PARTIAL"} else ControlCenterRuntimeState.UNKNOWN,
        readiness_state=ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {item.value for item in ControlCenterReadinessState} else "UNKNOWN"),
        warnings=payload.get("warnings") or [],
        errors=payload.get("errors") or [],
    ).to_dict()
    return {**envelope, **payload, "data": payload}
