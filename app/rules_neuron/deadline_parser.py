from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.rules_neuron.contracts import bounded
from app.utils.time_utils import parse_datetime


def parse_deadline_from_rules(rules_text: str | None) -> datetime | None:
    if not rules_text:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)", rules_text)
    if match:
        return parse_datetime(match.group(1))
    return None


def detect_ambiguous_deadline_terms(rules_text: str | None) -> list[str]:
    lower = (rules_text or "").lower()
    terms = []
    for phrase in ("end of day", "eod", "before", "after", "around", "no later than", "local time", "market close"):
        if phrase in lower:
            terms.append(phrase)
    if any(term in lower for term in ("end of day", "eod")) and not any(tz in lower for tz in ("utc", "et", "eastern", "gmt")):
        terms.append("timezone unclear")
    return sorted(set(terms))


def compare_deadline_to_market_close(deadline: datetime | None, close_time: datetime | None) -> dict[str, Any]:
    if deadline is None or close_time is None:
        return {"conflict": False, "reason": "deadline or close_time missing"}
    delta = abs((deadline - close_time).total_seconds())
    if delta > 86400:
        return {"conflict": True, "reason": "deadline differs from market close by more than 24h"}
    return {"conflict": False, "reason": "deadline aligns with close_time"}


def compute_deadline_risk(rules_text: str | None, deadline: datetime | None = None, close_time: datetime | None = None) -> dict[str, Any]:
    ambiguous = detect_ambiguous_deadline_terms(rules_text)
    parsed = deadline or parse_deadline_from_rules(rules_text)
    conflict = compare_deadline_to_market_close(parsed, close_time)
    risk = 0.0
    reasons: list[str] = []
    if parsed is None:
        risk += 0.45
        reasons.append("deadline missing")
    if ambiguous:
        risk += 0.25
        reasons.extend(ambiguous)
    if conflict["conflict"]:
        risk += 0.35
        reasons.append(conflict["reason"])
    return {"deadline_at": parsed, "risk": bounded(risk), "ambiguous_terms": ambiguous, "reasons": reasons}

