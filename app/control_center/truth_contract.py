from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TruthContractError(ValueError):
    """Raised when a Control Center response would overstate available truth."""


class ControlCenterStatus(StrEnum):
    REAL = "REAL"
    STALE = "STALE"
    MISSING = "MISSING"
    ERROR = "ERROR"
    LOCKED = "LOCKED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    PARTIAL = "PARTIAL"


class ControlCenterTruthState(StrEnum):
    ACTIVE_FRESH = "ACTIVE_FRESH"
    LAST_KNOWN = "LAST_KNOWN"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ControlCenterFreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"


class ControlCenterRuntimeState(StrEnum):
    RUNNING = "RUNNING"
    REGISTERED = "REGISTERED"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ControlCenterReadinessState(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


SOURCE_REQUIRED_STATUSES = {
    ControlCenterStatus.REAL,
    ControlCenterStatus.STALE,
    ControlCenterStatus.PARTIAL,
}


class ControlCenterTruthEnvelope(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: ControlCenterStatus
    source: str | None
    last_updated: str | None = None
    stale_after_seconds: int | None = Field(default=None, ge=0)
    age_seconds: float | None = Field(default=None, ge=0)
    freshness_state: ControlCenterFreshnessState = ControlCenterFreshnessState.MISSING
    runtime_state: ControlCenterRuntimeState = ControlCenterRuntimeState.UNKNOWN
    truth_state: ControlCenterTruthState
    readiness_state: ControlCenterReadinessState = ControlCenterReadinessState.UNKNOWN
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @field_validator("source")
    @classmethod
    def _normalize_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("data", mode="before")
    @classmethod
    def _data_must_be_object(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TruthContractError("data must be an object/dict")
        return value

    @field_validator("warnings", "errors", mode="before")
    @classmethod
    def _list_fields_must_be_arrays(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TruthContractError("warnings and errors must always be arrays")
        return [str(item) for item in value]

    @model_validator(mode="after")
    def _validate_truth_rules(self) -> ControlCenterTruthEnvelope:
        status = ControlCenterStatus(self.status)
        truth_state = ControlCenterTruthState(self.truth_state)

        if status in SOURCE_REQUIRED_STATUSES and not self.source:
            raise TruthContractError(f"{status.value} requires source")
        if truth_state == ControlCenterTruthState.HISTORICAL_ONLY and not self.source:
            raise TruthContractError("HISTORICAL_ONLY truth requires source")
        if status == ControlCenterStatus.REAL and truth_state == ControlCenterTruthState.UNKNOWN:
            raise TruthContractError("REAL cannot use truth_state UNKNOWN")
        if status == ControlCenterStatus.STALE and (
            self.stale_after_seconds is None or not self.last_updated
        ):
            raise TruthContractError("STALE requires last_updated and stale_after_seconds")
        if status == ControlCenterStatus.MISSING and not (self.warnings or self.errors):
            raise TruthContractError("MISSING must explain missing source/data")
        if status == ControlCenterStatus.ERROR and not self.errors:
            raise TruthContractError("ERROR requires at least one error")
        if status == ControlCenterStatus.NOT_IMPLEMENTED and self.data:
            raise TruthContractError("NOT_IMPLEMENTED must not pretend to have live data")
        if status == ControlCenterStatus.LOCKED and not (self.warnings or self.errors):
            raise TruthContractError("LOCKED must explain what is locked")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def truth_envelope(
    *,
    status: ControlCenterStatus | str,
    source: str | None,
    truth_state: ControlCenterTruthState | str,
    data: dict[str, Any] | None = None,
    last_updated: str | datetime | None = None,
    stale_after_seconds: int | None = None,
    age_seconds: float | None = None,
    freshness_state: ControlCenterFreshnessState | str | None = None,
    runtime_state: ControlCenterRuntimeState | str | None = None,
    readiness_state: ControlCenterReadinessState | str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> ControlCenterTruthEnvelope:
    return ControlCenterTruthEnvelope(
        status=ControlCenterStatus(status),
        source=source,
        last_updated=_serialize_timestamp(last_updated),
        stale_after_seconds=stale_after_seconds,
        age_seconds=age_seconds,
        freshness_state=ControlCenterFreshnessState(freshness_state or _freshness_for_status(status)),
        runtime_state=ControlCenterRuntimeState(runtime_state or _runtime_for_status(status)),
        truth_state=ControlCenterTruthState(truth_state),
        readiness_state=ControlCenterReadinessState(readiness_state or _readiness_for_status(status)),
        data=data or {},
        warnings=warnings or [],
        errors=errors or [],
    )


def not_implemented_envelope(
    *,
    source: str,
    warnings: list[str] | None = None,
) -> ControlCenterTruthEnvelope:
    return truth_envelope(
        status=ControlCenterStatus.NOT_IMPLEMENTED,
        source=source,
        truth_state=ControlCenterTruthState.UNKNOWN,
        data={},
        warnings=warnings
        or [
            "Control Center Truth Contract is defined, but full Control Center APIs are not implemented.",
            "No live data, PnL, health, positions, runtime status, or controls are exposed here.",
        ],
        errors=[],
    )


def control_center_truth_contract_demo() -> dict[str, Any]:
    return not_implemented_envelope(source="control_center_truth_contract").to_dict()


def require_pnl_source(source: str | None) -> None:
    _require_source("PnL", source, ("ledger", "capital"))


def require_health_source(source: str | None) -> None:
    _require_source("Health", source, ("heartbeat", "service_health"))


def require_decision_source(source: str | None) -> None:
    _require_source("Decision", source, ("evidence", "source"))


def require_candidate_truth_state(truth_state: ControlCenterTruthState | str | None) -> None:
    if truth_state is None:
        raise TruthContractError("Candidate requires truth_state")
    ControlCenterTruthState(truth_state)


def require_runtime_status_source(source: str | None) -> None:
    _require_source("Runtime status", source, ("runtime", "source", "state"))


def require_positions_source(source: str | None) -> None:
    _require_source("Positions", source, ("position", "paper_positions"))


def require_events_source(source: str | None) -> None:
    _require_source("Events", source, ("event",))


def _require_source(domain: str, source: str | None, required_terms: tuple[str, ...]) -> None:
    normalized = (source or "").strip().lower()
    if not normalized:
        raise TruthContractError(f"{domain} requires source")
    if not any(term in normalized for term in required_terms):
        terms = ", ".join(required_terms)
        raise TruthContractError(f"{domain} source must reference one of: {terms}")


def _serialize_timestamp(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return value


def _freshness_for_status(status: ControlCenterStatus | str) -> ControlCenterFreshnessState:
    normalized = ControlCenterStatus(status)
    if normalized == ControlCenterStatus.REAL:
        return ControlCenterFreshnessState.FRESH
    if normalized == ControlCenterStatus.STALE:
        return ControlCenterFreshnessState.STALE
    return ControlCenterFreshnessState.MISSING


def _runtime_for_status(status: ControlCenterStatus | str) -> ControlCenterRuntimeState:
    normalized = ControlCenterStatus(status)
    if normalized == ControlCenterStatus.REAL:
        return ControlCenterRuntimeState.RUNNING
    if normalized in {ControlCenterStatus.STALE, ControlCenterStatus.PARTIAL}:
        return ControlCenterRuntimeState.STALE
    if normalized == ControlCenterStatus.LOCKED:
        return ControlCenterRuntimeState.BLOCKED
    return ControlCenterRuntimeState.UNKNOWN


def _readiness_for_status(status: ControlCenterStatus | str) -> ControlCenterReadinessState:
    normalized = ControlCenterStatus(status)
    if normalized == ControlCenterStatus.REAL:
        return ControlCenterReadinessState.READY
    if normalized == ControlCenterStatus.PARTIAL:
        return ControlCenterReadinessState.PARTIAL
    if normalized == ControlCenterStatus.LOCKED:
        return ControlCenterReadinessState.BLOCKED
    if normalized in {ControlCenterStatus.STALE, ControlCenterStatus.MISSING, ControlCenterStatus.ERROR}:
        return ControlCenterReadinessState.NOT_READY
    return ControlCenterReadinessState.UNKNOWN
