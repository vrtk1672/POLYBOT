from __future__ import annotations

from app.rules_neuron.contracts import bounded


AMBIGUOUS_PATTERNS: dict[str, str] = {
    "likely": "probabilistic wording",
    "expected": "expectation rather than event",
    "significant": "unclear threshold",
    "official": "official source may be undefined",
    "confirmed": "confirmation standard may be unclear",
    "announced": "announcement differs from implementation",
    "reported": "reporting may differ from official confirmation",
    "substantially": "unclear magnitude",
    "majority": "threshold ambiguity",
    "by end of day": "timezone boundary ambiguity",
    "around": "time boundary ambiguity",
    "before": "boundary ambiguity",
    "after": "boundary ambiguity",
    "will happen": "scope ambiguity",
    "according to": "source dependency",
    "final": "finality may be revised",
    "resolved by": "manual resolution dependency",
}


def detect_ambiguous_terms(text: str | None) -> list[dict[str, object]]:
    lower = (text or "").lower()
    return [{"term": term, "reason": reason, "risk": classify_term_risk(term)} for term, reason in AMBIGUOUS_PATTERNS.items() if term in lower]


def classify_term_risk(term: str) -> float:
    high = {"announced", "reported", "by end of day", "resolved by", "before", "after", "will happen"}
    medium = {"official", "confirmed", "significant", "majority", "final"}
    if term in high:
        return 0.75
    if term in medium:
        return 0.55
    return 0.35


def ambiguity_score(terms: list[dict[str, object]]) -> float:
    if not terms:
        return 0.0
    return bounded(sum(float(term.get("risk") or 0) for term in terms) / max(len(terms), 1) + min(len(terms) * 0.04, 0.2))

