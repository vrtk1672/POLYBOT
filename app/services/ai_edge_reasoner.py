from __future__ import annotations

import json
from typing import Any


ALLOWED_AI_EDGE_STATES = {
    "EDGE_SUPPORTED",
    "EDGE_WEAK",
    "EDGE_WATCH",
    "NO_SOURCE_BACKED_EDGE",
    "SOURCE_CONFLICT",
    "EDGE_STALE",
    "EDGE_MISSING_DIRECTION",
    "EDGE_MISSING_CANDIDATE_IDENTITY",
    "EDGE_MISSING_PRICE",
    "EDGE_MISSING_LIQUIDITY",
    "EDGE_UNKNOWN",
}


def validate_ai_edge_review(raw: str | dict[str, Any] | None, *, allowed_source_ids: set[str]) -> dict[str, Any]:
    """Validate AI edge-review JSON without letting AI create evidence.

    AI review is supporting commentary only. It cannot introduce source ids,
    probabilities, execution permission, or trade approvals.
    """
    if raw is None:
        return _unavailable("AI_REVIEW_UNAVAILABLE")
    data: dict[str, Any]
    if isinstance(raw, dict):
        data = dict(raw)
    else:
        try:
            parsed = json.loads(str(raw))
        except Exception:
            extracted = _extract_json_object(str(raw))
            if not extracted:
                return _unavailable("AI_REVIEW_MALFORMED")
            try:
                parsed = json.loads(extracted)
            except Exception:
                return _unavailable("AI_REVIEW_MALFORMED")
        if not isinstance(parsed, dict):
            return _unavailable("AI_REVIEW_MALFORMED")
        data = parsed

    cited = {str(item) for item in data.get("cited_source_record_ids") or data.get("source_record_ids") or []}
    invented = sorted(cited - set(allowed_source_ids))
    if invented:
        return {
            "status": "REJECTED",
            "ai_review_status": "REJECTED_INVENTED_SOURCE",
            "blocker": "AI_INVENTED_SOURCE_IDS",
            "invented_source_record_ids": invented,
            "model": data.get("model") or data.get("ai_review_model"),
            "summary": "AI review was rejected because it cited source ids that were not provided.",
            "confidence": 0.0,
        }

    if data.get("fair_probability_estimate") is not None or data.get("expected_edge") is not None:
        return {
            "status": "REJECTED",
            "ai_review_status": "REJECTED_INVENTED_PROBABILITY",
            "blocker": "AI_INVENTED_PROBABILITY",
            "model": data.get("model") or data.get("ai_review_model"),
            "summary": "AI review was rejected because it attempted to provide unsupported probability or expected edge.",
            "confidence": 0.0,
        }

    edge_state = str(data.get("edge_state") or "EDGE_UNKNOWN").upper()
    if edge_state not in ALLOWED_AI_EDGE_STATES:
        edge_state = "EDGE_UNKNOWN"

    return {
        "status": "OK",
        "ai_review_status": "VALIDATED",
        "edge_state": edge_state,
        "summary": str(data.get("summary") or data.get("ai_thesis") or ""),
        "counter_thesis": str(data.get("counter_thesis") or data.get("ai_counter_thesis") or ""),
        "model": data.get("model") or data.get("ai_review_model") or "unknown",
        "confidence": _bounded(data.get("confidence"), default=0.0),
        "cited_source_record_ids": sorted(cited),
    }


def deterministic_ai_review(thesis: dict[str, Any], *, status: str = "UNAVAILABLE") -> dict[str, Any]:
    return {
        "status": status,
        "ai_review_status": status,
        "edge_state": thesis.get("edge_state") or "EDGE_UNKNOWN",
        "summary": thesis.get("ai_thesis") or thesis.get("blocker_code") or "AI review unavailable; deterministic edge thesis used.",
        "counter_thesis": thesis.get("ai_counter_thesis") or "No AI counter-thesis available.",
        "model": "deterministic_fallback",
        "confidence": 0.0,
        "cited_source_record_ids": [],
    }


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "ai_review_status": reason,
        "edge_state": "EDGE_UNKNOWN",
        "summary": reason,
        "counter_thesis": "",
        "model": "none",
        "confidence": 0.0,
        "cited_source_record_ids": [],
    }


def _bounded(value: Any, *, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default
