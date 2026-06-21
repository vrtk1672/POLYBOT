from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


NEURON_TYPES = {
    "ORDERBOOK",
    "NEWS",
    "WHALE",
    "RISK",
    "EXIT",
    "CAPITAL",
    "AI",
    "MEMORY",
    "CROSS_MARKET",
    "SIGNAL",
    "SOCIAL",
    "PAYOUT",
    "LIQUIDITY",
    "COORDINATOR",
    "LIFECYCLE",
    "CANDIDATE",
    "MARKET",
    "ACTIONABILITY",
    "SAFETY",
    "OTHER",
}

RESPONSE_STATES = {"SUPPORTED", "OPPOSED", "NEUTRAL", "WATCH", "BLOCKED", "STALE", "MISSING", "UNAVAILABLE", "ERROR"}
SUPPORT_DIRECTIONS = {"YES", "NO", "NEUTRAL", "CONFLICT", "UNKNOWN"}


def mesh_response(
    *,
    neuron_name: str,
    neuron_type: str,
    identity: dict[str, Any],
    response_state: str,
    supports_side: str = "UNKNOWN",
    confidence: float = 0.0,
    strength: float = 0.0,
    freshness_seconds: int | None = None,
    source_backed: bool = False,
    summary: str = "",
    reason: str = "",
    blocker_code: str | None = None,
    required_to_pass: list[str] | None = None,
    source_records: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "neuron_name": _required_name(neuron_name),
        "neuron_type": _enum(str(neuron_type or "OTHER").upper(), NEURON_TYPES, "OTHER"),
        "candidate_id": _text(identity.get("candidate_id")),
        "market_id": _text(identity.get("market_id")),
        "condition_id": _text(identity.get("condition_id")),
        "side": _side(identity.get("side")),
        "token_id": _text(identity.get("token_id")),
        "correlation_id": _text(identity.get("correlation_id")),
        "event_id": _text(identity.get("event_id")),
        "response_state": _enum(str(response_state or "UNKNOWN").upper(), RESPONSE_STATES, "ERROR"),
        "supports_side": _enum(str(supports_side or "UNKNOWN").upper(), SUPPORT_DIRECTIONS, "UNKNOWN"),
        "confidence": _bounded(confidence),
        "strength": _bounded(strength),
        "freshness_seconds": freshness_seconds if isinstance(freshness_seconds, int) and freshness_seconds >= 0 else None,
        "source_backed": bool(source_backed),
        "summary": summary or "",
        "reason": reason or summary or "",
        "blocker_code": blocker_code,
        "required_to_pass": list(required_to_pass or []),
        "source_records": list(source_records or []),
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "metadata": dict(metadata or {}),
    }
    validate_mesh_response(payload)
    return payload


def unavailable_response(
    *,
    neuron_name: str,
    neuron_type: str,
    identity: dict[str, Any],
    reason: str,
    blocker_code: str = "ORGAN_UNAVAILABLE",
    required_to_pass: list[str] | None = None,
) -> dict[str, Any]:
    return mesh_response(
        neuron_name=neuron_name,
        neuron_type=neuron_type,
        identity=identity,
        response_state="UNAVAILABLE",
        supports_side="UNKNOWN",
        confidence=0.0,
        strength=0.0,
        source_backed=False,
        summary=reason,
        reason=reason,
        blocker_code=blocker_code,
        required_to_pass=required_to_pass or [f"Provide a Mesh-native adapter or source for {neuron_name}."],
    )


def validate_mesh_response(payload: dict[str, Any]) -> dict[str, Any]:
    required = {
        "neuron_name",
        "neuron_type",
        "candidate_id",
        "market_id",
        "condition_id",
        "side",
        "token_id",
        "correlation_id",
        "event_id",
        "response_state",
        "supports_side",
        "confidence",
        "strength",
        "source_backed",
        "summary",
        "reason",
        "blocker_code",
        "required_to_pass",
        "source_records",
        "created_at",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"mesh response missing required fields: {missing}")
    if payload["neuron_type"] not in NEURON_TYPES:
        raise ValueError(f"invalid neuron_type: {payload['neuron_type']}")
    if payload["response_state"] not in RESPONSE_STATES:
        raise ValueError(f"invalid response_state: {payload['response_state']}")
    if payload["supports_side"] not in SUPPORT_DIRECTIONS:
        raise ValueError(f"invalid supports_side: {payload['supports_side']}")
    for field in ("confidence", "strength"):
        value = payload[field]
        if not isinstance(value, (int, float)) or value < 0 or value > 1:
            raise ValueError(f"{field} must be in [0, 1]")
    if not isinstance(payload["required_to_pass"], list):
        raise ValueError("required_to_pass must be a list")
    if not isinstance(payload["source_records"], list):
        raise ValueError("source_records must be a list")
    return payload


def identity_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": bundle.get("candidate_id"),
        "market_id": bundle.get("market_id"),
        "condition_id": bundle.get("condition_id"),
        "side": bundle.get("side"),
        "token_id": bundle.get("token_id"),
        "correlation_id": bundle.get("correlation_id"),
        "event_id": bundle.get("event_id"),
    }


def _required_name(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        raise ValueError("neuron_name is required")
    return text


def _enum(value: str, allowed: set[str], fallback: str) -> str:
    return value if value in allowed else fallback


def _bounded(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _side(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in {"YES", "NO"} else None
