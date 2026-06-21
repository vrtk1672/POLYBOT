from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


SEVERITY_BY_CODE = {
    "PAPER_SIMULATION_OFF": "SAFETY_BLOCK",
    "SYSTEM_POWER_OFF": "SAFETY_BLOCK",
    "RUNTIME_STOPPED": "SAFETY_BLOCK",
    "GOVERNOR_DENIED_PAPER": "SAFETY_BLOCK",
    "MISSING_CANDIDATE_EVENT_LINK": "MISSING_DATA",
    "MARKET_SCOPED_ONLY_EVENT": "HARD_BLOCK",
    "MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE": "HARD_BLOCK",
    "AMBIGUOUS_CANDIDATE_EVENT_LINK": "HARD_BLOCK",
    "TOKEN_SIDE_MISMATCH": "HARD_BLOCK",
    "STALE_CANDIDATE_EVENT_LINK": "STALE_DATA",
    "WAITING_FOR_PRICE_REFRESH": "WAITING_ON_REFRESH",
    "MISSING_TRUSTED_ORDERBOOK": "MISSING_DATA",
    "STALE_ORDERBOOK": "STALE_DATA",
    "BLOCKED_BY_RISK": "HARD_BLOCK",
    "BLOCKED_BY_RISK_REVIEW": "HARD_BLOCK",
    "BLOCKED_BY_EXIT": "HARD_BLOCK",
    "BLOCKED_BY_CAPITAL": "HARD_BLOCK",
    "BLOCKED_BY_CAPITAL_WATCH": "HARD_BLOCK",
    "BLOCKED_BY_LIFECYCLE": "GOVERNANCE_DENIED",
    "BLOCKED_BY_DUPLICATE": "SAFETY_BLOCK",
    "BLOCKED_BY_OPEN_POSITION": "SAFETY_BLOCK",
    "WAITING_FOR_LIFECYCLE": "WAITING_ON_REFRESH",
    "WAITING_FOR_CAPITAL": "WAITING_ON_REFRESH",
    "WAITING_FOR_RISK": "WAITING_ON_REFRESH",
    "WAITING_FOR_EXIT": "WAITING_ON_REFRESH",
    "LIFECYCLE_GOVERNANCE_DENIED": "GOVERNANCE_DENIED",
    "NO_CANDIDATE_SCOPED_EVENT": "HARD_BLOCK",
    "NO_PAPER_ACTIONABILITY": "HARD_BLOCK",
    "DUPLICATE_ACTIVE_INTENT_RISK": "SAFETY_BLOCK",
    "OPEN_PAPER_POSITION_CONFLICT": "SAFETY_BLOCK",
}


REQUIRED_BY_CODE = {
    "PAPER_SIMULATION_OFF": "Paper Simulation must remain OFF before certification; Phase 10 must explicitly enable it only after pre-checks pass.",
    "SYSTEM_POWER_OFF": "SYSTEM ON smoke must start and stop cleanly before certification.",
    "RUNTIME_STOPPED": "Runtime supervisor must be alive during controlled smoke.",
    "GOVERNOR_DENIED_PAPER": "State Governor must explicitly allow paper before any later paper phase.",
    "MISSING_CANDIDATE_EVENT_LINK": "A fresh event must link to the candidate by market, side, and token.",
    "MARKET_SCOPED_ONLY_EVENT": "Candidate-targeted refresh must produce candidate-scoped event metadata.",
    "MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE": "Market-level events cannot be used for candidate paper actionability; candidate-scoped event metadata is required.",
    "AMBIGUOUS_CANDIDATE_EVENT_LINK": "Dedupe or select exactly one candidate for the event market/side/token.",
    "TOKEN_SIDE_MISMATCH": "Candidate token/side must match the orderbook event token/side.",
    "STALE_CANDIDATE_EVENT_LINK": "Candidate/event link must refresh within freshness TTL.",
    "WAITING_FOR_PRICE_REFRESH": "Candidate-specific trusted orderbook must be refreshed before paper actionability.",
    "MISSING_TRUSTED_ORDERBOOK": "Trusted orderbook evidence must be attached to the exact candidate.",
    "STALE_ORDERBOOK": "Orderbook must be fresh within execution TTL.",
    "BLOCKED_BY_RISK": "Risk opinion must become non-blocking.",
    "BLOCKED_BY_RISK_REVIEW": "Risk must approve the candidate; RISK_REVIEW/RISK_WATCH is observation-only and cannot create paper intent.",
    "BLOCKED_BY_EXIT": "Exit opinion and exit plan must be ready.",
    "BLOCKED_BY_CAPITAL": "Capital opinion must be OK.",
    "BLOCKED_BY_CAPITAL_WATCH": "Risk-Capital policy must reach CAPITAL_SUPPORT/CAPITAL_OK; CAPITAL_WATCH is observation-only for strict paper.",
    "BLOCKED_BY_LIFECYCLE": "Lifecycle opinion must allow paper intent progression.",
    "BLOCKED_BY_DUPLICATE": "Duplicate active paper intent risk must clear before candidate paper actionability.",
    "BLOCKED_BY_OPEN_POSITION": "Open paper position conflict must clear before candidate paper actionability.",
    "WAITING_FOR_LIFECYCLE": "A fresh lifecycle opinion must be available before candidate paper actionability.",
    "WAITING_FOR_CAPITAL": "A fresh capital opinion must be available before candidate paper actionability.",
    "WAITING_FOR_RISK": "A fresh risk opinion must be available before candidate paper actionability.",
    "WAITING_FOR_EXIT": "A fresh exit opinion must be available before candidate paper actionability.",
    "LIFECYCLE_GOVERNANCE_DENIED": "Lifecycle governance blockers must clear.",
    "NO_CANDIDATE_SCOPED_EVENT": "At least one high-confidence candidate-scoped event must exist.",
    "NO_PAPER_ACTIONABILITY": "At least one candidate must map to a paper actionability state.",
    "DUPLICATE_ACTIVE_INTENT_RISK": "Duplicate active paper intents for the same market/side must be resolved.",
    "OPEN_PAPER_POSITION_CONFLICT": "Open paper position conflicts must be closed or explicitly excluded.",
}


def unified_blocker(
    blocker_code: str,
    *,
    source: str,
    candidate_id: str | None = None,
    event_id: str | None = None,
    correlation_id: str | None = None,
    market_id: str | None = None,
    side: str | None = None,
    token_id: str | None = None,
    severity: str | None = None,
    required_to_pass: str | list[str] | None = None,
    is_refreshable: bool | None = None,
    is_operator_action_required: bool | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    code = str(blocker_code or "UNKNOWN_BLOCKER").upper()
    required = required_to_pass if required_to_pass is not None else REQUIRED_BY_CODE.get(code, "Source must provide a specific condition to clear this blocker.")
    if isinstance(required, str):
        required_list = [required]
    else:
        required_list = [str(item) for item in required]
    sev = severity or SEVERITY_BY_CODE.get(code, "UNKNOWN")
    refreshable = is_refreshable if is_refreshable is not None else sev in {"WAITING_ON_REFRESH", "STALE_DATA", "MISSING_DATA"}
    operator = is_operator_action_required if is_operator_action_required is not None else sev in {"SAFETY_BLOCK", "GOVERNANCE_DENIED", "HARD_BLOCK"}
    return {
        "blocker_code": code,
        "severity": sev,
        "source": source,
        "candidate_id": candidate_id,
        "event_id": event_id,
        "correlation_id": correlation_id,
        "market_id": market_id,
        "side": side,
        "token_id": token_id,
        "required_to_pass": required_list,
        "is_refreshable": bool(refreshable),
        "is_operator_action_required": bool(operator),
        "created_at": created_at or datetime.now(UTC).isoformat(),
    }


def unified_blockers(
    blockers: list[str] | tuple[str, ...] | None,
    *,
    source: str,
    candidate_id: str | None = None,
    event_id: str | None = None,
    correlation_id: str | None = None,
    market_id: str | None = None,
    side: str | None = None,
    token_id: str | None = None,
) -> list[dict[str, Any]]:
    return [
        unified_blocker(
            str(code),
            source=source,
            candidate_id=candidate_id,
            event_id=event_id,
            correlation_id=correlation_id,
            market_id=market_id,
            side=side,
            token_id=token_id,
        )
        for code in (blockers or [])
    ]
