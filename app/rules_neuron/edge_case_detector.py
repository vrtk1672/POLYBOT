from __future__ import annotations


EDGE_PATTERNS = {
    "postponed": "postponed/cancelled event",
    "cancelled": "postponed/cancelled event",
    "draw": "tie/draw rules unclear",
    "tie": "tie/draw rules unclear",
    "revised": "source revision after deadline",
    "multiple official": "multiple possible official sources",
    "announced": "announced vs implemented",
    "implemented": "announced vs implemented",
    "confirmed": "confirmed vs reported",
    "reported": "confirmed vs reported",
    "before": "before/after boundary ambiguity",
    "after": "before/after boundary ambiguity",
    "timezone": "timezone ambiguity",
    "if and only if": "conditional resolution",
    "discretion": "manual discretion",
}


def detect_edge_cases(rules_text: str | None, question: str | None = None, category: str | None = None) -> list[str]:
    lower = " ".join([rules_text or "", question or "", category or ""]).lower()
    return sorted({label for pattern, label in EDGE_PATTERNS.items() if pattern in lower})


def detect_dangerous_edge_cases(edge_cases: list[str]) -> list[str]:
    dangerous_labels = {"postponed/cancelled event", "announced vs implemented", "before/after boundary ambiguity", "timezone ambiguity", "conditional resolution", "manual discretion"}
    return [case for case in edge_cases if case in dangerous_labels]


def detect_contradictions(rules_text: str | None) -> list[str]:
    lower = (rules_text or "").lower()
    contradictions = []
    if "will resolve yes" in lower and "will resolve no" in lower:
        contradictions.append("contains both yes and no resolution language")
    if "announced" in lower and "implemented" in lower:
        contradictions.append("announced and implemented standards both present")
    if "before" in lower and "after" in lower:
        contradictions.append("before and after boundary terms both present")
    return contradictions


def detect_scope_ambiguity(rules_text: str | None, question: str | None = None) -> list[str]:
    lower = " ".join([rules_text or "", question or ""]).lower()
    findings = []
    if "will happen" in lower:
        findings.append("event threshold unclear")
    if "significant" in lower or "substantial" in lower:
        findings.append("magnitude threshold unclear")
    return findings

