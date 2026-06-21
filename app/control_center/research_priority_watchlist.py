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
from app.services.research_priority_watchlist import ResearchPriorityWatchlistService


class ResearchPriorityWatchlistControlService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._service = ResearchPriorityWatchlistService(connection_factory=self._factory)

    def get_summary(self, *, limit: int = 10) -> dict[str, Any]:
        return _envelope(self._service.summary(limit=limit))

    def refresh(self, *, limit: int = 500, force: bool = False) -> dict[str, Any]:
        result = self._service.refresh(limit=limit, force=force)
        payload = self._service.summary(limit=10)
        payload["latest_priority_action"] = result
        return _envelope(payload)

    def by_market(self, *, market_id: str) -> dict[str, Any]:
        return _envelope(_result_payload("research_priority_watchlist by-market", self._service.by_market(market_id=market_id)))

    def due(self, *, limit: int = 50) -> dict[str, Any]:
        return _envelope(_result_payload("research_priority_watchlist due", self._service.due(limit=limit)))


def _result_payload(source: str, result: dict[str, Any]) -> dict[str, Any]:
    rows = result.get("due_markets") or ([result.get("watchlist")] if result.get("watchlist") else [])
    return {
        "status": "REAL" if rows else result.get("status", "MISSING"),
        "source": source,
        "last_updated": datetime.now(UTC).isoformat(),
        "freshness_state": "FRESH" if rows else "MISSING",
        "readiness_state": "READY" if rows else "UNKNOWN",
        "truth_state": "ACTIVE_FRESH" if rows else "UNKNOWN",
        "result": result,
        "warnings": [] if rows else ["No research priority watchlist rows matched this query."],
        "errors": [],
    }


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status_value = payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL"
    envelope = truth_envelope(
        status=ControlCenterStatus(status_value),
        source=str(payload.get("source") or "research_priority_watchlist"),
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
