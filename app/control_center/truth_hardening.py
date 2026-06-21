from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterTruthState,
)


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def age_seconds(value: Any, *, now: datetime | None = None) -> float | None:
    timestamp = parse_timestamp(value)
    if timestamp is None:
        return None
    now = now or datetime.now(UTC)
    return max(0.0, (now - timestamp).total_seconds())


def classify_freshness(
    value: Any,
    *,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> tuple[ControlCenterFreshnessState, float | None]:
    age = age_seconds(value, now=now)
    if age is None:
        return ControlCenterFreshnessState.MISSING, None
    if age > stale_after_seconds:
        return ControlCenterFreshnessState.STALE, age
    return ControlCenterFreshnessState.FRESH, age


def truth_from_freshness(freshness: ControlCenterFreshnessState, *, has_history: bool) -> ControlCenterTruthState:
    if freshness == ControlCenterFreshnessState.FRESH:
        return ControlCenterTruthState.ACTIVE_FRESH
    if freshness == ControlCenterFreshnessState.STALE:
        return ControlCenterTruthState.LAST_KNOWN if has_history else ControlCenterTruthState.REFRESH_REQUIRED
    return ControlCenterTruthState.HISTORICAL_ONLY if has_history else ControlCenterTruthState.UNKNOWN


def classify_service_runtime(row: dict[str, Any], *, stale_after_seconds: int = 600) -> dict[str, Any]:
    heartbeat_at = row.get("last_heartbeat_at")
    success_at = row.get("last_success_at")
    updated_at = row.get("updated_at")
    status = str(row.get("status") or "UNKNOWN").upper()
    freshness, age = classify_freshness(heartbeat_at or success_at or updated_at, stale_after_seconds=stale_after_seconds)

    if status in {"ERROR", "DEGRADED", "BLOCKED_BY_MODE"}:
        runtime_state = ControlCenterRuntimeState.BLOCKED
        readiness_state = ControlCenterReadinessState.BLOCKED
    elif status == "STOPPED":
        runtime_state = ControlCenterRuntimeState.STOPPED
        readiness_state = ControlCenterReadinessState.NOT_READY
    elif heartbeat_at is None and success_at is None:
        runtime_state = ControlCenterRuntimeState.REGISTERED
        readiness_state = ControlCenterReadinessState.PARTIAL
    elif freshness == ControlCenterFreshnessState.STALE:
        runtime_state = ControlCenterRuntimeState.STALE
        readiness_state = ControlCenterReadinessState.NOT_READY
    elif status in {"RUNNING", "HEALTHY"}:
        runtime_state = ControlCenterRuntimeState.RUNNING
        readiness_state = ControlCenterReadinessState.READY
    else:
        runtime_state = ControlCenterRuntimeState.UNKNOWN
        readiness_state = ControlCenterReadinessState.UNKNOWN

    warnings: list[str] = []
    if runtime_state == ControlCenterRuntimeState.REGISTERED:
        warnings.append("REGISTERED_SERVICE_WITHOUT_HEARTBEAT_OR_SUCCESS")
    if runtime_state == ControlCenterRuntimeState.STALE:
        warnings.append("SERVICE_HEARTBEAT_OR_SUCCESS_IS_STALE")
    if readiness_state == ControlCenterReadinessState.BLOCKED:
        warnings.append(f"SERVICE_STATUS_{status}")

    payload = dict(row)
    if status == "HEALTHY":
        payload["status"] = "RUNNING"

    return {
        **payload,
        "age_seconds": age,
        "freshness_state": freshness.value,
        "runtime_state": runtime_state.value,
        "readiness_state": readiness_state.value,
        "truth_state": truth_from_freshness(freshness, has_history=bool(heartbeat_at or success_at or updated_at)).value,
        "truth_warnings": warnings,
    }


def readiness_from_blockers(blockers: list[str], *, has_partial: bool = False) -> ControlCenterReadinessState:
    if blockers:
        return ControlCenterReadinessState.BLOCKED
    if has_partial:
        return ControlCenterReadinessState.PARTIAL
    return ControlCenterReadinessState.READY
