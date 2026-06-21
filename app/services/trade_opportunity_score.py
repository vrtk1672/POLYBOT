from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any


FULL_PAPER_THRESHOLD = 75.0
PAPER_OBSERVATION_THRESHOLD = 60.0
WATCH_THRESHOLD = 40.0

FULL_PAPER_BAND = "FULL_PAPER_CERTIFICATION"
PAPER_OBSERVATION_BAND = "PAPER_OBSERVATION"
WATCH_ONLY_BAND = "WATCH_ONLY"
NO_TRADE_BAND = "NO_TRADE"
HARD_BLOCKED_BAND = "HARD_BLOCKED"

APPROVED_RISK_STATES = {"RISK_OK", "RISK_ALLOWED", "RISK_SUPPORT", "RISK_APPROVED"}
REVIEW_RISK_STATES = {"RISK_REVIEW", "RISK_REVIEW_LINEAGE_PARTIAL", "RISK_WATCH"}
BLOCKED_RISK_STATES = {"RISK_BLOCKED", "RISK_BLOCKED_CAPITAL", "RISK_BLOCKED_STALE_SOURCE", "RISK_BLOCKED_WEAK_EDGE", "RISK_BLOCKED_SOURCE_CONFLICT"}

CAPITAL_SUPPORT_STATES = {"CAPITAL_SUPPORT", "CAPITAL_OK", "CAPITAL_ALLOWED", "CAPITAL_EFFICIENCY_OK"}
CAPITAL_WATCH_STATES = {"CAPITAL_WATCH", "WATCH", "CAPITAL_REVIEW"}
CAPITAL_BLOCK_STATES = {"CAPITAL_BLOCK", "CAPITAL_BLOCKED", "CAPITAL_INSUFFICIENT_DATA"}

EXIT_READY_STATES = {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}
VALID_EVENT_SCOPES = {"CANDIDATE_ACTIONABLE", "CANDIDATE_SCOPED", "CANDIDATE_TARGETED_REFRESH"}
VALID_LINK_STATES = {"LINKED_TO_CANDIDATE", "HIGH_CONFIDENCE_LINK", "CANDIDATE_LINKED"}

SCORE_FORMULA = (
    "overall_score = 0.18*edge_quality + 0.14*source_confidence + "
    "0.14*trade_thesis + 0.14*profit_potential + 0.14*capital_efficiency + "
    "0.12*exit_quality + 0.08*timing + 0.06*confidence - 0.30*risk_penalty"
)


def attach_opportunity_score(item: dict[str, Any]) -> dict[str, Any]:
    score = score_actionability_item(item)
    item["opportunity_score"] = score
    item["opportunity_score_id"] = score["opportunity_score_id"]
    item["decision_band"] = score["decision_band"]
    item["paper_observation_eligible"] = score["decision_band"] == PAPER_OBSERVATION_BAND
    item["full_paper_certification_ready"] = score["decision_band"] == FULL_PAPER_BAND
    item["opportunity_score_components"] = score["components"]
    item["opportunity_hard_blockers"] = score["hard_blockers"]
    item["opportunity_soft_blockers"] = score["soft_blockers"]
    item["opportunity_required_to_improve"] = score["required_to_improve"]
    return item


def score_actionability_item(item: dict[str, Any]) -> dict[str, Any]:
    components = {
        "profit_potential_score": _profit_potential_score(item),
        "edge_quality_score": _edge_quality_score(item),
        "source_confidence_score": _source_confidence_score(item),
        "trade_thesis_score": _trade_thesis_score(item),
        "capital_efficiency_score": _capital_efficiency_component(item),
        "exit_quality_score": _exit_quality_score(item),
        "risk_penalty_score": _risk_penalty_score(item),
        "timing_score": _timing_score(item),
        "confidence_score": _confidence_score(item),
    }
    weighted = (
        0.18 * components["edge_quality_score"]
        + 0.14 * components["source_confidence_score"]
        + 0.14 * components["trade_thesis_score"]
        + 0.14 * components["profit_potential_score"]
        + 0.14 * components["capital_efficiency_score"]
        + 0.12 * components["exit_quality_score"]
        + 0.08 * components["timing_score"]
        + 0.06 * components["confidence_score"]
    )
    overall = round(_clamp(weighted - (0.30 * components["risk_penalty_score"]), 0.0, 100.0), 2)
    hard_blockers = _hard_blockers(item)
    soft_blockers = _soft_blockers(item)
    required_to_improve = _required_to_improve(item, hard_blockers, soft_blockers)
    band = _decision_band(item, overall, hard_blockers)
    created_at = datetime.now(UTC).isoformat()
    return {
        "opportunity_score_id": _score_id(item),
        "candidate_id": item.get("candidate_id"),
        "market_id": item.get("market_id"),
        "condition_id": (item.get("edge_thesis") or {}).get("condition_id") if isinstance(item.get("edge_thesis"), dict) else None,
        "side": item.get("side"),
        "token_id": item.get("token_id"),
        "source_refresh_cycle_id": item.get("source_refresh_cycle_id"),
        "mesh_inquiry_session_id": (item.get("propagation_context") or {}).get("mesh_inquiry_session_id") if isinstance(item.get("propagation_context"), dict) else None,
        "edge_thesis_id": item.get("edge_thesis_id"),
        "trade_thesis_id": item.get("thesis_id"),
        "risk_evidence_id": item.get("risk_evidence_id"),
        "capital_efficiency_id": item.get("capital_evidence_id"),
        "exit_plan_id": item.get("exit_plan_id"),
        "lifecycle_decision_id": item.get("lifecycle_decision_id"),
        "candidate_event_scope": item.get("candidate_event_scope") or item.get("candidate_event_actionability_scope"),
        "candidate_event_link_state": item.get("candidate_event_link_state"),
        "token_side_match": _event_link_ok(item),
        "orderbook_freshness_state": item.get("orderbook_freshness_state") or item.get("candidate_trusted_orderbook_state") or item.get("candidate_price_path_state"),
        "selected_orderbook_snapshot_id": item.get("selected_orderbook_snapshot_id") or item.get("candidate_price_orderbook_snapshot_id") or item.get("orderbook_snapshot_id"),
        "selected_candidate_event_id": item.get("selected_candidate_event_id") or item.get("event_id"),
        "market_memory_id": item.get("market_memory_id"),
        "market_memory_status": item.get("market_memory_status"),
        "market_memory_freshness": item.get("market_memory_freshness"),
        "market_identity_verification_state": item.get("market_identity_verification_state"),
        "token_verification_state": item.get("token_verification_state"),
        "market_memory_research_priority": item.get("market_memory_research_priority"),
        "research_watchlist_id": item.get("research_watchlist_id"),
        "research_priority_band": item.get("research_priority_band"),
        "research_priority_score": item.get("research_priority_score"),
        "research_priority_reasons": item.get("priority_reasons") or [],
        "watchlist_scheduler_state": item.get("watchlist_scheduler_state"),
        "next_refresh_due_at": item.get("next_refresh_due_at"),
        "recent_source_event_count": item.get("recent_source_event_count") or 0,
        "strongest_event_link_type": item.get("strongest_event_link_type"),
        "strongest_event_link_confidence": item.get("strongest_event_link_confidence") or 0.0,
        "recent_directional_event_state": item.get("recent_directional_event_state") or "UNKNOWN",
        "recent_source_event_link_state": item.get("recent_source_event_link_state") or "EVENT_NOT_LINKED",
        "recall_link_state": item.get("recall_link_state") or item.get("recent_source_event_link_state") or "EVENT_NOT_LINKED",
        "event_link_actionability_hint": item.get("event_link_actionability_hint") or "NOT_RELEVANT",
        "token_side_resolution_state": item.get("token_side_resolution_state") or "TOKEN_SIDE_UNKNOWN",
        "event_link_guardrail_reason": item.get("event_link_guardrail_reason"),
        "direct_event_link_count": item.get("direct_event_link_count") or 0,
        "likely_event_link_count": item.get("likely_event_link_count") or 0,
        "source_event_memory_ids": item.get("source_event_memory_ids") or [],
        "event_to_market_link_ids": item.get("event_to_market_link_ids") or [],
        "targeted_revalidation_id": item.get("targeted_revalidation_id"),
        "latest_targeted_revalidation_state": item.get("latest_targeted_revalidation_state") or "MISSING",
        "orderbook_refresh_state_from_revalidation": item.get("orderbook_refresh_state_from_revalidation") or "UNKNOWN",
        "refreshed_orderbook_snapshot_id": item.get("refreshed_orderbook_snapshot_id"),
        "movement_state_from_revalidation": item.get("movement_state_from_revalidation") or "UNKNOWN",
        "already_priced_in_state_from_revalidation": item.get("already_priced_in_state_from_revalidation") or "UNKNOWN",
        "revalidation_candidate_generation_later_state": item.get("revalidation_candidate_generation_later_state") or "NOT_EVALUATED",
        "candidate_generation_later_eligible": bool(item.get("candidate_generation_later_eligible")),
        "proactive_seed_id": item.get("proactive_seed_id") or item.get("latest_proactive_candidate_seed_id"),
        "seed_type": item.get("seed_type"),
        "multi_trigger_id": item.get("multi_trigger_id"),
        "trigger_type": item.get("trigger_type"),
        "trigger_score": item.get("trigger_score"),
        "trigger_reasons": item.get("trigger_reasons") or item.get("trigger_reasons_json") or [],
        "seed_generation_source": item.get("seed_generation_source"),
        "proactive_seed_research_only": item.get("research_only"),
        "proactive_seed_execution_allowed": item.get("seed_execution_allowed"),
        "proactive_seed_paper_allowed": item.get("seed_paper_allowed"),
        "proactive_seed_shadow_allowed": item.get("seed_shadow_allowed"),
        "proactive_seed_live_allowed": item.get("seed_live_allowed"),
        "mesh_handoff_state": item.get("mesh_handoff_state"),
        "seed_mesh_inquiry_id": item.get("seed_mesh_inquiry_id"),
        "seed_mesh_adapter_payload_id": item.get("seed_mesh_adapter_payload_id") or item.get("adapter_payload_id"),
        "seed_mesh_adapter_result_state": item.get("seed_mesh_adapter_result_state") or item.get("adapter_result_state"),
        "seed_mesh_result_state": item.get("seed_mesh_result_state"),
        "seed_mesh_edge_state": item.get("seed_mesh_edge_state"),
        "seed_mesh_trade_thesis_state": item.get("seed_mesh_trade_thesis_state"),
        "seed_mesh_opportunity_decision_band": item.get("seed_mesh_opportunity_decision_band"),
        "seed_mesh_research_only": item.get("seed_mesh_research_only"),
        "observation_policy_review_id": item.get("paper_observation_policy_review_id") or item.get("observation_policy_review_id"),
        "observation_policy_state": item.get("paper_observation_policy_state") or item.get("observation_policy_state"),
        "observation_allowed_by_policy": bool(item.get("observation_allowed_by_policy")),
        "observation_policy_blockers": item.get("observation_policy_blockers") or [],
        "observation_execution_mode_implemented": bool(item.get("observation_execution_mode_implemented")),
        "overall_score": overall,
        **components,
        "components": components,
        "decision_band": band,
        "paper_observation_eligible": band == PAPER_OBSERVATION_BAND,
        "full_paper_certification_ready": band == FULL_PAPER_BAND,
        "learning_only": band == PAPER_OBSERVATION_BAND,
        "execution_authority": "NONE_DATA_ONLY",
        "hard_blockers": hard_blockers,
        "soft_blockers": soft_blockers,
        "watch_reasons": _watch_reasons(item, band, soft_blockers),
        "required_to_improve": required_to_improve,
        "score_formula": SCORE_FORMULA,
        "score_explanation": _score_explanation(band, overall, hard_blockers, soft_blockers),
        "created_at": created_at,
    }


def summarize_opportunity_scores(items: list[dict[str, Any]]) -> dict[str, int]:
    scores = [_score_payload(item) for item in items]
    return {
        "full_paper_certification": sum(1 for score in scores if score.get("decision_band") == FULL_PAPER_BAND),
        "paper_observation_eligible": sum(1 for score in scores if score.get("decision_band") == PAPER_OBSERVATION_BAND),
        "watch_only": sum(1 for score in scores if score.get("decision_band") == WATCH_ONLY_BAND),
        "no_trade": sum(1 for score in scores if score.get("decision_band") == NO_TRADE_BAND),
        "hard_blocked": sum(1 for score in scores if score.get("decision_band") == HARD_BLOCKED_BAND),
    }


def _score_payload(item: dict[str, Any]) -> dict[str, Any]:
    score = item.get("opportunity_score")
    return score if isinstance(score, dict) else score_actionability_item(item)


def _decision_band(item: dict[str, Any], overall: float, hard_blockers: list[str]) -> str:
    if hard_blockers:
        return HARD_BLOCKED_BAND
    strict = item.get("strict_paper_qualification") if isinstance(item.get("strict_paper_qualification"), dict) else {}
    risk_state = _upper(item.get("risk_gate_state"))
    capital_state = _capital_state(item)
    exit_state = _upper(item.get("exit_gate_state") or item.get("exit_readiness_state"))
    if strict.get("qualified") is True and risk_state in APPROVED_RISK_STATES and capital_state in CAPITAL_SUPPORT_STATES and exit_state in EXIT_READY_STATES and overall >= FULL_PAPER_THRESHOLD:
        return FULL_PAPER_BAND
    if _paper_observation_candidate(item) and overall >= PAPER_OBSERVATION_THRESHOLD:
        return PAPER_OBSERVATION_BAND
    if overall >= WATCH_THRESHOLD:
        return WATCH_ONLY_BAND
    return NO_TRADE_BAND


def _paper_observation_candidate(item: dict[str, Any]) -> bool:
    edge_state = _upper(item.get("edge_state"))
    risk_state = _upper(item.get("risk_gate_state"))
    capital_state = _capital_state(item)
    thesis_state = _thesis_status(item)
    return (
        edge_state in {"EDGE_SUPPORTED", "EDGE_WATCH"}
        and bool(item.get("source_backed"))
        and thesis_state == "THESIS_SUPPORTED"
        and _upper(item.get("exit_gate_state") or item.get("exit_readiness_state")) in EXIT_READY_STATES
        and risk_state not in BLOCKED_RISK_STATES
        and capital_state not in CAPITAL_BLOCK_STATES
        and _event_link_ok(item)
        and not _has_stale_critical_evidence(item)
    )


def _hard_blockers(item: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    scope = _upper(item.get("candidate_event_scope") or item.get("candidate_event_actionability_scope"))
    link = _upper(item.get("candidate_event_link_state"))
    if scope and scope not in VALID_EVENT_SCOPES:
        blockers.append("candidate_event_scope_not_actionable")
    if link == "TOKEN_SIDE_MISMATCH":
        blockers.append("token_side_mismatch")
    elif link and link not in VALID_LINK_STATES:
        blockers.append("missing_candidate_event_link")
    elif not link:
        blockers.append("missing_candidate_event_link")
    if item.get("edge_state") == "EDGE_STALE" or item.get("stale_sources_blocking"):
        blockers.append("stale_critical_source")
    orderbook_state = _upper(item.get("candidate_trusted_orderbook_state") or item.get("candidate_price_path_state"))
    if "STALE" in orderbook_state or "MISSING" in orderbook_state or "STALE_ORDERBOOK" in set(item.get("blockers") or []):
        blockers.append("stale_orderbook")
    if not item.get("thesis_id") or _thesis_status(item) in {"", "THESIS_MISSING", "THESIS_REJECTED", "THESIS_UNKNOWN"}:
        blockers.append("missing_trade_thesis")
    if not item.get("exit_intent") or _upper(item.get("exit_intent")) == "UNKNOWN_EXIT":
        blockers.append("missing_exit_intent")
    if _upper(item.get("exit_gate_state") or item.get("exit_readiness_state")) not in EXIT_READY_STATES:
        blockers.append("exit_not_ready")
    risk_state = _upper(item.get("risk_gate_state"))
    if risk_state in BLOCKED_RISK_STATES or risk_state.startswith("RISK_BLOCKED"):
        blockers.append("risk_hard_blocked")
    if _capital_state(item) in CAPITAL_BLOCK_STATES:
        blockers.append("capital_hard_blocked")
    trace = item.get("lifecycle_gate_trace") if isinstance(item.get("lifecycle_gate_trace"), dict) else {}
    critical = trace.get("critical_blockers") or []
    if trace and trace.get("actionability_class") == "LIFECYCLE_DENIED":
        blockers.append("lifecycle_denied_hard")
    if any(_upper(code) in {"SOURCE_CONFLICT", "SOURCE_CONFLICT_CRITICAL"} for code in critical):
        blockers.append("source_conflict_critical")
    if not item.get("expected_hold_time_hours") and _upper(item.get("exit_intent")) not in {"HOLD_TO_RESOLUTION", ""}:
        blockers.append("missing_dynamic_hold_time")
    if "BLOCKED_BY_DUPLICATE" in set(item.get("blockers") or []) or "BLOCKED_BY_OPEN_POSITION" in set(item.get("blockers") or []):
        blockers.append("duplicate_or_open_position_conflict")
    if _upper(item.get("operational_paper_execution_state")) in {"EXECUTION_MODE_UNSAFE", "LIVE_ENABLED", "SHADOW_ENABLED"}:
        blockers.append("unsafe_execution_mode")
    return _unique(blockers)


def _soft_blockers(item: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    risk_state = _upper(item.get("risk_gate_state"))
    if risk_state in REVIEW_RISK_STATES:
        blockers.append("risk_review_not_full_paper_ready")
    capital_state = _capital_state(item)
    if capital_state in CAPITAL_WATCH_STATES:
        blockers.append("capital_watch_not_full_paper_ready")
    if not _reward_evidence_present(item):
        blockers.append("reward_evidence_weak_or_missing")
    if _to_float(item.get("dynamic_rpdh")) is not None and (_to_float(item.get("dynamic_rpdh")) or 0.0) < 0.01:
        blockers.append("reward_per_dollar_hour_low")
    if _upper((item.get("joined_trade_thesis") or {}).get("ai_review_state") if isinstance(item.get("joined_trade_thesis"), dict) else None) in {"REJECTED", "FAILED"}:
        blockers.append("ai_thesis_review_negative")
    return _unique(blockers)


def _required_to_improve(item: dict[str, Any], hard: list[str], soft: list[str]) -> list[str]:
    required = list(item.get("required_to_pass") or [])
    if "risk_review_not_full_paper_ready" in soft:
        required.append("Risk must move from review/partial lineage to approved before Full Paper Certification.")
    if "capital_watch_not_full_paper_ready" in soft:
        required.append("Capital efficiency must move from watch to support before Full Paper Certification.")
    if "reward_evidence_weak_or_missing" in soft:
        required.append("Provide explicit expected reward or price-move evidence for stronger profit potential scoring.")
    if "missing_candidate_event_link" in hard:
        required.append("Candidate event must be linked to the selected candidate/side/token.")
    if "token_side_mismatch" in hard:
        required.append("Candidate event token and side must match the selected actionability row.")
    if "missing_trade_thesis" in hard:
        required.append("Create a supported candidate-scoped trade thesis.")
    if "missing_dynamic_hold_time" in hard:
        required.append("Provide thesis-backed expected hold time and hold-time source.")
    return _unique([str(item) for item in required if item])


def _watch_reasons(item: dict[str, Any], band: str, soft: list[str]) -> list[str]:
    reasons = list(soft)
    if band == PAPER_OBSERVATION_BAND:
        reasons.append("learning_only_not_execution_authority")
    if band == WATCH_ONLY_BAND and item.get("edge_state"):
        reasons.append(f"edge_state_{item.get('edge_state')}")
    return _unique(reasons)


def _edge_quality_score(item: dict[str, Any]) -> float:
    state = _upper(item.get("edge_state"))
    edge = _fraction_or_percent(item.get("edge_score"))
    if state == "EDGE_SUPPORTED":
        return _clamp(82.0 + edge * 18.0 if item.get("source_backed") else 65.0 + edge * 15.0)
    if state == "EDGE_WATCH":
        return _clamp(45.0 + edge * 20.0)
    if state == "EDGE_WEAK":
        return 30.0
    if state == "EDGE_STALE":
        return 10.0
    if state == "SOURCE_CONFLICT":
        return 5.0
    return 20.0


def _source_confidence_score(item: dict[str, Any]) -> float:
    score = 35.0
    if item.get("source_backed") is True:
        score += 20.0
    score += min(len(item.get("fresh_sources_used") or []) * 6.0, 18.0)
    score += min(float(item.get("directional_sources_found") or 0) * 5.0, 15.0)
    if _event_link_ok(item):
        score += 12.0
    if item.get("stale_sources_blocking"):
        score -= 30.0
    return _clamp(score)


def _trade_thesis_score(item: dict[str, Any]) -> float:
    thesis = item.get("joined_trade_thesis") if isinstance(item.get("joined_trade_thesis"), dict) else {}
    status = _thesis_status(item)
    if status == "THESIS_SUPPORTED":
        confidence = _fraction_or_percent(thesis.get("thesis_confidence") or item.get("thesis_confidence"))
        exit_conf = _fraction_or_percent(thesis.get("exit_confidence") or item.get("exit_confidence"))
        return _clamp(68.0 + confidence * 20.0 + exit_conf * 12.0)
    if status == "THESIS_WATCH":
        return 48.0
    if status:
        return 20.0
    return 0.0


def _profit_potential_score(item: dict[str, Any]) -> float:
    thesis = item.get("joined_trade_thesis") if isinstance(item.get("joined_trade_thesis"), dict) else {}
    expected_reward = _to_float(thesis.get("expected_reward") or item.get("expected_reward"))
    expected_move = _to_float(thesis.get("expected_price_move") or item.get("expected_price_move"))
    trace = item.get("risk_capital_gate_trace") if isinstance(item.get("risk_capital_gate_trace"), dict) else {}
    rpdh = _to_float(item.get("dynamic_rpdh") or trace.get("dynamic_reward_per_dollar_hour"))
    if expected_reward is not None and expected_reward > 0:
        return _clamp(55.0 + min(expected_reward * 6.0, 30.0) + (10.0 if expected_move and expected_move > 0 else 0.0))
    if rpdh is None:
        return 30.0 if item.get("edge_state") == "EDGE_SUPPORTED" else 15.0
    if rpdh >= 0.10:
        return 92.0
    if rpdh >= 0.05:
        return 80.0
    if rpdh >= 0.01:
        return 65.0
    if rpdh > 0:
        return 42.0
    return 20.0


def _capital_efficiency_component(item: dict[str, Any]) -> float:
    trace = item.get("risk_capital_gate_trace") if isinstance(item.get("risk_capital_gate_trace"), dict) else {}
    raw = _to_float(item.get("capital_efficiency_after_thesis") or trace.get("capital_efficiency_score"))
    if raw is not None:
        return _clamp(raw * 100.0 if raw <= 1.0 else raw)
    if _capital_state(item) in CAPITAL_SUPPORT_STATES:
        return 75.0
    if _capital_state(item) in CAPITAL_WATCH_STATES:
        return 48.0
    return 25.0


def _exit_quality_score(item: dict[str, Any]) -> float:
    state = _upper(item.get("exit_gate_state") or item.get("exit_readiness_state"))
    trace = item.get("exit_gate_trace") if isinstance(item.get("exit_gate_trace"), dict) else {}
    liquidity = _upper(trace.get("liquidity_state") or trace.get("liquidity_exit_quality"))
    if state in EXIT_READY_STATES:
        score = 72.0
        if liquidity == "GOOD":
            score += 15.0
        elif liquidity == "FAIR":
            score += 8.0
        elif liquidity in {"POOR", "EXIT_LIQUIDITY_UNKNOWN"}:
            score -= 18.0
        return _clamp(score)
    if state:
        return 20.0
    return 5.0


def _risk_penalty_score(item: dict[str, Any]) -> float:
    penalty = 0.0
    risk_state = _upper(item.get("risk_gate_state"))
    if risk_state in REVIEW_RISK_STATES:
        penalty += 28.0
    elif risk_state in BLOCKED_RISK_STATES or risk_state.startswith("RISK_BLOCKED"):
        penalty += 75.0
    elif risk_state not in APPROVED_RISK_STATES:
        penalty += 35.0
    capital_state = _capital_state(item)
    if capital_state in CAPITAL_WATCH_STATES:
        penalty += 12.0
    elif capital_state in CAPITAL_BLOCK_STATES:
        penalty += 45.0
    if "SOURCE_CONFLICT" in set(_upper(code) for code in (item.get("blockers") or [])):
        penalty += 35.0
    return _clamp(penalty)


def _timing_score(item: dict[str, Any]) -> float:
    hours = _to_float(item.get("expected_hold_time_hours"))
    if hours is None or hours <= 0:
        return 35.0 if _upper(item.get("exit_intent")) == "HOLD_TO_RESOLUTION" else 15.0
    if hours <= 6:
        return 85.0
    if hours <= 24:
        return 78.0
    if hours <= 72:
        return 70.0
    if hours <= 24 * 14:
        return 50.0
    return 25.0


def _confidence_score(item: dict[str, Any]) -> float:
    checks = [
        item.get("candidate_id"),
        item.get("market_id"),
        item.get("side"),
        item.get("token_id"),
        item.get("edge_thesis_id"),
        item.get("risk_evidence_id"),
        item.get("thesis_id"),
        item.get("lifecycle_decision_id"),
        item.get("source_refresh_cycle_id"),
        _event_link_ok(item),
    ]
    return round(100.0 * sum(1 for check in checks if check) / len(checks), 2)


def _score_explanation(band: str, overall: float, hard: list[str], soft: list[str]) -> str:
    if band == HARD_BLOCKED_BAND:
        return f"Hard blocked despite score {overall}: {', '.join(hard)}."
    if band == FULL_PAPER_BAND:
        return f"Full Paper Certification quality score {overall}; strict qualification and approved gates pass."
    if band == PAPER_OBSERVATION_BAND:
        return f"Learning-only Paper Observation quality score {overall}; blocked from Full Paper by {', '.join(soft) if soft else 'current policy review'}."
    if band == WATCH_ONLY_BAND:
        return f"Watch-only score {overall}; continue monitoring until blockers improve."
    return f"No-trade score {overall}; opportunity quality is below watch threshold."


def _score_id(item: dict[str, Any]) -> str:
    raw = "|".join(str(item.get(key) or "") for key in ("candidate_id", "side", "token_id", "source_refresh_cycle_id", "edge_thesis_id", "thesis_id", "lifecycle_decision_id"))
    return f"opportunity_score_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _event_link_ok(item: dict[str, Any]) -> bool:
    return _upper(item.get("candidate_event_scope") or item.get("candidate_event_actionability_scope")) in VALID_EVENT_SCOPES and _upper(item.get("candidate_event_link_state")) in VALID_LINK_STATES


def _has_stale_critical_evidence(item: dict[str, Any]) -> bool:
    return item.get("stale_gate_selected") is True or bool(item.get("stale_sources_blocking")) or "STALE_ORDERBOOK" in set(item.get("blockers") or [])


def _reward_evidence_present(item: dict[str, Any]) -> bool:
    thesis = item.get("joined_trade_thesis") if isinstance(item.get("joined_trade_thesis"), dict) else {}
    trace = item.get("risk_capital_gate_trace") if isinstance(item.get("risk_capital_gate_trace"), dict) else {}
    return any(_to_float(value) is not None for value in (thesis.get("expected_reward"), thesis.get("expected_price_move"), item.get("dynamic_rpdh"), trace.get("dynamic_reward_per_dollar_hour")))


def _thesis_status(item: dict[str, Any]) -> str:
    thesis = item.get("joined_trade_thesis") if isinstance(item.get("joined_trade_thesis"), dict) else {}
    trace = item.get("trade_thesis_trace") if isinstance(item.get("trade_thesis_trace"), dict) else {}
    return _upper(thesis.get("status") or item.get("trade_thesis_status") or trace.get("status"))


def _capital_state(item: dict[str, Any]) -> str:
    trace = item.get("risk_capital_gate_trace") if isinstance(item.get("risk_capital_gate_trace"), dict) else {}
    return _upper(trace.get("risk_capital_policy_state") or trace.get("classification") or item.get("risk_capital_policy_state") or item.get("capital_gate_state"))


def _fraction_or_percent(value: Any) -> float:
    raw = _to_float(value)
    if raw is None:
        return 0.0
    return _clamp(raw / 100.0 if raw > 1.0 else raw, 0.0, 1.0)


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _upper(value: Any) -> str:
    return str(value or "").upper()


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, float(value))), 2)


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out
