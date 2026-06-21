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
from app.services.market_universe_memory import MarketUniverseMemoryService


class MarketUniverseMemoryControlService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._service = MarketUniverseMemoryService(connection_factory=self._factory)

    def get_summary(self, *, limit: int = 10) -> dict[str, Any]:
        payload = self._service.summary(limit=limit)
        return _envelope(payload)

    def refresh(self, *, force: bool = False, limit: int | None = None) -> dict[str, Any]:
        result = self._service.refresh_universe(force=force, limit=limit)
        payload = self._service.summary(limit=10)
        payload["latest_refresh_action"] = result
        return _envelope(payload)

    def lookup(
        self,
        *,
        market_id: str | None = None,
        condition_id: str | None = None,
        token_id: str | None = None,
        slug: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        result = self._service.lookup(market_id=market_id, condition_id=condition_id, token_id=token_id, slug=slug, title=title)
        payload = {
            "status": "REAL" if result.get("match") else "MISSING",
            "source": "market_universe_memory lookup",
            "last_updated": datetime.now(UTC).isoformat(),
            "freshness_state": "FRESH" if result.get("match") else "MISSING",
            "readiness_state": "READY" if result.get("match") else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if result.get("match") else "UNKNOWN",
            "lookup": {
                "market_id": market_id,
                "condition_id": condition_id,
                "token_id": token_id,
                "slug": slug,
                "title": title,
            },
            "result": result,
            "warnings": [] if result.get("match") else ["No market universe memory row matched the lookup keys."],
            "errors": [],
        }
        return _envelope(payload)


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status_value = payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL"
    envelope = truth_envelope(
        status=ControlCenterStatus(status_value),
        source=str(payload.get("source") or "market_universe_memory"),
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
