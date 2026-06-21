from __future__ import annotations

from enum import StrEnum


class MeshSessionType(StrEnum):
    MARKET_SESSION = "MARKET_SESSION"
    CANDIDATE_SESSION = "CANDIDATE_SESSION"
    POSITION_SESSION = "POSITION_SESSION"
    OPPORTUNITY_SESSION = "OPPORTUNITY_SESSION"
    THREAT_SESSION = "THREAT_SESSION"
    GLOBAL_SESSION = "GLOBAL_SESSION"
    UNASSIGNED_SESSION = "UNASSIGNED_SESSION"


SESSION_TYPES = {item.value for item in MeshSessionType}


ADVERSE_EVENT_TYPES = {
    "RISK_CHANGED",
    "EXIT_CHANGED",
    "NO_TRADE_RECORDED",
}


POSITIVE_EVENT_TYPES = {
    "PAPER_INTENT_CREATED",
    "TRUSTED_ORDERBOOK_CREATED",
}


def is_adverse_event(event: dict[str, object]) -> bool:
    event_type = str(event.get("event_type") or "")
    payload = event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {}
    if event_type in ADVERSE_EVENT_TYPES:
        return True
    if payload.get("threat_context") is True or payload.get("adverse") is True:
        return True
    decision_text = " ".join(
        str(payload.get(key) or "")
        for key in ("decision", "status", "risk_status", "exit_status", "primary_reason")
    ).upper()
    return any(token in decision_text for token in ("BLOCK", "REJECT", "INSUFFICIENT", "THREAT", "INVALID"))


def is_opportunity_event(event: dict[str, object]) -> bool:
    event_type = str(event.get("event_type") or "")
    payload = event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {}
    if event_type in POSITIVE_EVENT_TYPES:
        return True
    if payload.get("opportunity_context") is True or payload.get("positive_signal") is True:
        return True
    decision_text = " ".join(
        str(payload.get(key) or "")
        for key in ("decision", "status", "risk_status", "exit_status", "eligibility_status")
    ).upper()
    return any(token in decision_text for token in ("APPROVE", "ELIGIBLE", "GOOD", "CLEAR", "TRUSTED"))
