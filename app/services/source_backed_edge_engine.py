from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.services.ai_edge_reasoner import deterministic_ai_review, validate_ai_edge_review


EDGE_TTL_SECONDS = 900
ORDERBOOK_WATCH_MAX = 0.44
EDGE_SUPPORTED_THRESHOLD = 0.70
EDGE_WATCH_THRESHOLD = 0.45
CONFLICT_THRESHOLD = 0.25


def build_edge_thesis(record: dict[str, Any], evidence: dict[str, Any], *, ai_review_raw: str | dict[str, Any] | None = None) -> dict[str, Any]:
    candidate_id = str(record.get("subject_id") or "") if record.get("subject_type") == "PAPER_CANDIDATE" else str(record.get("candidate_id") or "")
    market_id = _text(record.get("market_id"))
    side = _side(record.get("side"))
    token_id = _text(record.get("token_id"))
    condition_id = _text(record.get("condition_id"))
    event_id = _text(record.get("event_id"))
    correlation_id = _text(record.get("correlation_id"))
    source_organ_status = _source_organ_status(evidence.get("mesh_responses") or [])
    contributions = _collect_contributions(record, evidence)
    supporting = [item for item in contributions if item["supports_side"] == side and item["source_type"] != "ORDERBOOK"]
    opposing = [item for item in contributions if item["supports_side"] in {"YES", "NO"} and item["supports_side"] != side and item["source_type"] != "ORDERBOOK"]
    orderbook_items = [item for item in contributions if item["source_type"] == "ORDERBOOK"]
    stale_items = [item for item in contributions if _is_stale(item) and (item["source_type"] == "ORDERBOOK" or item["supports_side"] in {"YES", "NO", "CONFLICT"})]
    fresh_supporting = [item for item in supporting if not _is_stale(item)]
    fresh_opposing = [item for item in opposing if not _is_stale(item)]
    fresh_orderbook_items = [item for item in orderbook_items if not _is_stale(item)]
    stale_supporting = [item for item in supporting if _is_stale(item)]
    support_score = _weighted_score(fresh_supporting)
    conflict_score = _weighted_score(fresh_opposing)
    orderbook_score = min(ORDERBOOK_WATCH_MAX, _weighted_score(orderbook_items))
    score = max(0.0, min(1.0, support_score + min(orderbook_score, 0.18) - conflict_score))

    missing_identity = [name for name, value in (("candidate_id", candidate_id), ("market_id", market_id), ("side", side), ("token_id", token_id)) if not value]
    blocker_code: str | None = None
    if missing_identity:
        edge_state = "EDGE_MISSING_CANDIDATE_IDENTITY"
        blocker_code = "EDGE_MISSING_CANDIDATE_IDENTITY"
    elif not orderbook_items:
        edge_state = "EDGE_MISSING_PRICE"
        blocker_code = "EDGE_MISSING_PRICE"
    elif orderbook_items and not fresh_orderbook_items:
        edge_state = "EDGE_STALE"
        blocker_code = "EDGE_STALE"
    elif stale_supporting and not fresh_supporting:
        edge_state = "EDGE_STALE"
        blocker_code = "EDGE_STALE"
    elif conflict_score >= CONFLICT_THRESHOLD and fresh_supporting:
        edge_state = "SOURCE_CONFLICT"
        blocker_code = "SOURCE_CONFLICT"
    elif not fresh_supporting and source_organ_status.get("all_unavailable"):
        edge_state = "EDGE_SOURCE_ORGANS_UNAVAILABLE"
        blocker_code = "EDGE_SOURCE_ORGANS_UNAVAILABLE"
        score = min(score, ORDERBOOK_WATCH_MAX)
    elif not fresh_supporting:
        edge_state = "DERIVED_SIGNALS_WATCH_ONLY" if fresh_orderbook_items and _has_fresh_watch_signal(contributions) else "EDGE_WATCH" if fresh_orderbook_items else "NO_CURRENT_DIRECTIONAL_EDGE"
        blocker_code = "NO_CURRENT_DIRECTIONAL_EDGE" if edge_state in {"DERIVED_SIGNALS_WATCH_ONLY", "EDGE_WATCH"} else "NO_SOURCE_BACKED_EDGE"
        score = min(score, ORDERBOOK_WATCH_MAX)
    elif score >= EDGE_SUPPORTED_THRESHOLD:
        edge_state = "EDGE_SUPPORTED"
    elif score >= EDGE_WATCH_THRESHOLD:
        edge_state = "EDGE_WATCH"
        blocker_code = "EDGE_WEAK"
    else:
        edge_state = "EDGE_WEAK"
        blocker_code = "EDGE_WEAK"

    source_backed = bool(fresh_supporting) and edge_state == "EDGE_SUPPORTED"
    risk_usable = source_backed and conflict_score < CONFLICT_THRESHOLD and not missing_identity
    allowed_source_ids = {str(item["source_record_id"]) for item in contributions if item.get("source_record_id")}
    ai_review = validate_ai_edge_review(ai_review_raw, allowed_source_ids=allowed_source_ids) if ai_review_raw else deterministic_ai_review({"edge_state": edge_state, "blocker_code": blocker_code})
    if ai_review.get("status") == "REJECTED":
        blocker_code = str(ai_review.get("blocker") or "AI_REVIEW_REJECTED")
        if edge_state == "EDGE_SUPPORTED":
            edge_state = "EDGE_WATCH"
            source_backed = False
            risk_usable = False
    stale_sources_blocking = stale_supporting if edge_state == "EDGE_STALE" else []
    stale_sources_ignored = [item for item in stale_items if item not in stale_sources_blocking]

    thesis = {
        "edge_thesis_id": _thesis_id(candidate_id, market_id, side, token_id, contributions, edge_state),
        "candidate_id": candidate_id or None,
        "market_id": market_id,
        "condition_id": condition_id,
        "side": side,
        "token_id": token_id,
        "correlation_id": correlation_id,
        "event_id": event_id,
        "edge_state": edge_state,
        "edge_score": round(score, 6),
        "source_backed": source_backed,
        "risk_usable": risk_usable,
        "primary_edge_type": _primary_edge_type(fresh_supporting, fresh_orderbook_items or orderbook_items),
        "supporting_neurons": sorted({item["neuron"] for item in fresh_supporting}),
        "opposing_neurons": sorted({item["neuron"] for item in fresh_opposing}),
        "supporting_sources": [_source_ref(item) for item in fresh_supporting],
        "opposing_sources": [_source_ref(item) for item in fresh_opposing],
        "market_price": _market_price(evidence.get("orderbook") or {}),
        "fair_probability_estimate": None,
        "expected_edge": None,
        "freshness_seconds": min([int(item["freshness_seconds"]) for item in contributions if item.get("freshness_seconds") is not None] or [0]),
        "confidence": round(min(1.0, max(score, _weighted_confidence(fresh_supporting))), 6),
        "ai_thesis": _thesis_summary(edge_state, fresh_supporting, fresh_opposing, fresh_orderbook_items or orderbook_items, blocker_code),
        "ai_counter_thesis": _counter_summary(edge_state, fresh_opposing, blocker_code),
        "ai_review_model": ai_review.get("model") or "deterministic_fallback",
        "ai_review_status": ai_review.get("ai_review_status") or ai_review.get("status"),
        "ai_review": ai_review,
        "blocker_code": blocker_code,
        "required_to_pass": _required_to_pass(edge_state, blocker_code, missing_identity),
        "created_at": datetime.now(UTC).isoformat(),
        "source_records": [_source_ref(item) for item in contributions],
        "source_contributions": contributions,
        "fresh_sources_used": [_source_ref(item) for item in fresh_supporting + fresh_opposing + fresh_orderbook_items],
        "stale_sources_ignored": [_source_ref(item) for item in stale_sources_ignored],
        "stale_sources_blocking": [_source_ref(item) for item in stale_sources_blocking],
        "directional_sources_used": [_source_ref(item) for item in fresh_supporting + fresh_opposing],
        "watch_only_sources": [_source_ref(item) for item in contributions if not _is_stale(item) and (item["source_type"] == "ORDERBOOK" or item["supports_side"] == "NEUTRAL")],
        "derived_signal_ids": [item["source_record_id"] for item in contributions if str(item.get("source_type")) == "NEURON_SIGNAL" and item.get("source_record_id")],
        "source_refresh_cycle_id": (evidence.get("source_refresh_context") or {}).get("source_refresh_cycle_id"),
        "propagation_context": {
            "source_refresh_cycle_id": (evidence.get("source_refresh_context") or {}).get("source_refresh_cycle_id"),
            "source_refresh_completed_at": (evidence.get("source_refresh_context") or {}).get("source_refresh_completed_at"),
            "candidate_id": candidate_id or None,
            "market_id": market_id,
            "condition_id": condition_id,
            "side": side,
            "token_id": token_id,
            "event_id": event_id,
            "correlation_id": correlation_id,
        },
        "source_organ_status": source_organ_status,
        "source_organs_queried": source_organ_status.get("queried", 0),
        "source_organs_unavailable": source_organ_status.get("unavailable_organs", []),
        "source_organs_no_data": source_organ_status.get("no_data_organs", []),
        "missing_source_organs": source_organ_status.get("missing_source_organs", []),
        "directional_sources_found": len([item for item in fresh_supporting + fresh_opposing if item["source_type"] != "ORDERBOOK"]),
        "conflict_score": round(conflict_score, 6),
        "support_score": round(support_score, 6),
        "orderbook_watch_score": round(orderbook_score, 6),
        "no_execution": True,
        "no_fake_edge": True,
        "no_fake_probability": True,
    }
    return thesis


def risk_mapping_from_thesis(thesis: dict[str, Any]) -> tuple[str, str]:
    state = str(thesis.get("edge_state") or "EDGE_UNKNOWN")
    if state == "EDGE_SUPPORTED" and thesis.get("risk_usable") is True:
        return str(thesis.get("primary_edge_type") or "MULTI_FACTOR_MESH_EDGE"), "SOURCE_BACKED_EDGE_PRESENT"
    if state == "DERIVED_SIGNALS_WATCH_ONLY":
        return "ORDERBOOK_LIQUIDITY_SETUP", "EDGE_WEAK"
    if state in {"EDGE_WATCH", "EDGE_WEAK"}:
        return str(thesis.get("primary_edge_type") or "ORDERBOOK_LIQUIDITY_SETUP"), "EDGE_WEAK"
    if state == "SOURCE_CONFLICT":
        return "MULTI_FACTOR_MESH_EDGE", "EDGE_UNKNOWN"
    if state == "EDGE_STALE":
        return str(thesis.get("primary_edge_type") or "UNKNOWN"), "EDGE_UNKNOWN"
    if state == "EDGE_SOURCE_ORGANS_UNAVAILABLE":
        return "SOURCE_ORGANS_UNAVAILABLE", "NO_SOURCE_BACKED_EDGE"
    if state == "NO_CURRENT_DIRECTIONAL_EDGE":
        return "NO_SOURCE_BACKED_EDGE", "NO_CURRENT_DIRECTIONAL_EDGE"
    return "NO_SOURCE_BACKED_EDGE", "NO_SOURCE_BACKED_EDGE"


def build_edge_thesis_from_mesh_responses(
    identity: dict[str, Any],
    responses: list[dict[str, Any]],
    *,
    ai_review_raw: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": identity.get("candidate_id"),
        "candidate_id": identity.get("candidate_id"),
        "market_id": identity.get("market_id"),
        "condition_id": identity.get("condition_id"),
        "side": identity.get("side"),
        "token_id": identity.get("token_id"),
        "correlation_id": identity.get("correlation_id"),
        "event_id": identity.get("event_id"),
    }
    return build_edge_thesis(record, {"mesh_responses": responses}, ai_review_raw=ai_review_raw)


def _collect_contributions(record: dict[str, Any], ev: dict[str, Any]) -> list[dict[str, Any]]:
    side = _side(record.get("side"))
    out: list[dict[str, Any]] = []
    book = ev.get("orderbook") or {}
    if book:
        spread = _decimal_or_none(book.get("spread"))
        liquidity = _decimal_or_none(book.get("liquidity_score") or book.get("depth_2c") or book.get("total_bid_depth") or book.get("total_ask_depth"))
        strength = Decimal("0.20")
        if spread is not None and spread <= Decimal("0.03"):
            strength += Decimal("0.10")
        if liquidity is not None and liquidity > 0:
            strength += Decimal("0.10")
        out.append(
            _contribution(
                neuron="orderbook",
                source_type="ORDERBOOK",
                supports_side=side or "NEUTRAL",
                confidence=0.62,
                strength=float(min(Decimal("0.44"), strength)),
                source_record_id=f"orderbook_snapshot:{book.get('orderbook_snapshot_id') or book.get('id')}",
                freshness_seconds=_age_seconds(book.get("collected_at") or book.get("snapshot_at") or book.get("created_at")),
                reason="Candidate-scoped trusted orderbook is fresh enough to support watch-level price context.",
                candidate_scoped=True,
                stale_after_seconds=180,
            )
        )
    payout = ev.get("payout") or {}
    risk_reward = _decimal_or_none(payout.get("risk_reward"))
    if payout and risk_reward is not None and risk_reward >= Decimal("1.0"):
        out.append(
            _contribution(
                neuron="payout",
                source_type="PAYOUT_ODDS",
                supports_side=side or "NEUTRAL",
                confidence=_float(payout.get("confidence"), default=0.65),
                strength=float(min(Decimal("1"), Decimal("0.35") + min(risk_reward - Decimal("1.0"), Decimal("1.0")) * Decimal("0.25"))),
                source_record_id=f"payout_odds_evaluations:{payout.get('evaluation_id') or payout.get('id')}",
                freshness_seconds=_age_seconds(payout.get("updated_at") or payout.get("created_at")),
                reason="Payout odds show source-backed price/reward asymmetry.",
                candidate_scoped=True,
            )
        )
    news = ev.get("news") or {}
    if news:
        out.append(
            _contribution(
                neuron="news",
                source_type="NEWS_CONTEXT",
                supports_side=_direction(news.get("direction")),
                confidence=_float(news.get("confidence"), default=0.5),
                strength=_float(news.get("strength"), default=0.0) * max(0.0, 1.0 - _float(news.get("already_priced_in"), default=0.0)),
                source_record_id=f"news_impact_scores:{news.get('impact_id') or news.get('id')}",
                freshness_seconds=_age_seconds(news.get("created_at")),
                reason=str(news.get("reason") or "News impact source exists for this market."),
                candidate_scoped=False,
            )
        )
    whale = ev.get("whale") or {}
    if whale:
        whale_side = _direction(whale.get("side") or whale.get("side_or_outcome"))
        size = _decimal_or_none(whale.get("size_usd") or whale.get("notional") or whale.get("size"))
        out.append(
            _contribution(
                neuron="whale",
                source_type="WHALE_CONTEXT",
                supports_side=whale_side,
                confidence=_float(whale.get("confidence"), default=0.5),
                strength=float(min(Decimal("1"), Decimal("0.35") + min(size or Decimal("0"), Decimal("10000")) / Decimal("25000"))),
                source_record_id=f"whale_events:{whale.get('whale_event_id') or whale.get('id')}",
                freshness_seconds=_age_seconds(whale.get("event_time") or whale.get("event_timestamp") or whale.get("created_at")),
                reason="Whale/flow source exists for this market and side.",
                candidate_scoped=False,
            )
        )
    social = ev.get("social") or {}
    if social:
        out.append(
            _contribution(
                neuron="social",
                source_type="SOCIAL_CONTEXT",
                supports_side=_direction(social.get("sentiment_direction")),
                confidence=_float(social.get("confidence"), default=0.5),
                strength=_float(social.get("link_score") or social.get("hype_pressure") or social.get("narrative_strength"), default=0.0),
                source_record_id=f"social_market_links:{social.get('social_link_id') or social.get('id')}",
                freshness_seconds=_age_seconds(social.get("created_at") or social.get("computed_at")),
                reason=str(social.get("link_reason") or "Social source exists for this market."),
                candidate_scoped=False,
            )
        )
    market_movement = ev.get("market_movement") or {}
    if market_movement:
        out.append(
            _contribution(
                neuron="market_movement",
                source_type="NEURON_SIGNAL",
                supports_side=_direction(market_movement.get("trend_direction")),
                confidence=_float(market_movement.get("data_completeness_score"), default=0.5),
                strength=_float(market_movement.get("trend_strength") or market_movement.get("technical_score"), default=0.0),
                source_record_id=f"market_technical_signals:{market_movement.get('id')}",
                freshness_seconds=_age_seconds(market_movement.get("ts") or market_movement.get("created_at")),
                reason=str(market_movement.get("market_regime") or "Market movement signal exists for this market."),
                candidate_scoped=False,
            )
        )
    memory = ev.get("memory") or {}
    if memory:
        memory_strength = max(_float(memory.get("news_reaction_score"), default=0.0), _float(memory.get("whale_reaction_score"), default=0.0))
        out.append(
            _contribution(
                neuron="memory",
                source_type="MEMORY_CONTEXT",
                supports_side="NEUTRAL",
                confidence=_float(memory.get("memory_confidence"), default=0.0),
                strength=memory_strength,
                source_record_id=f"market_memory_v2:{memory.get('id') or memory.get('market_id')}",
                freshness_seconds=_age_seconds(memory.get("updated_at") or memory.get("last_updated_at")),
                reason=f"Market memory status={memory.get('memory_status') or 'unknown'}.",
                candidate_scoped=False,
            )
        )
    for signal in ev.get("neuron_signals") or []:
        out.append(
            _contribution(
                neuron=str(signal.get("neuron") or "unknown"),
                source_type="NEURON_SIGNAL",
                supports_side=_signal_direction(signal.get("raw_direction")),
                confidence=_float(signal.get("confidence"), default=0.0),
                strength=_float(signal.get("strength"), default=0.0),
                source_record_id=f"neuron_signals:{signal.get('signal_id') or signal.get('id')}",
                freshness_seconds=_age_seconds(signal.get("created_at")),
                reason=str((signal.get("evidence_json") or {}).get("reason") or signal.get("event_type") or "Neuron signal observed."),
                candidate_scoped=False,
            )
        )
    for response in ev.get("mesh_responses") or []:
        if str(response.get("response_state") or "").upper() in {"UNAVAILABLE", "MISSING", "ERROR"}:
            continue
        candidate_linked = _mesh_response_candidate_linked(response)
        out.append(
            _contribution(
                neuron=str(response.get("neuron_name") or "unknown"),
                source_type=_mesh_source_type(response),
                supports_side=_direction(response.get("supports_side")),
                confidence=_float(response.get("confidence"), default=0.0),
                strength=_float(response.get("strength"), default=0.0) if candidate_linked or _mesh_source_type(response) == "ORDERBOOK" else 0.0,
                source_record_id=_mesh_response_source_id(response),
                freshness_seconds=_mesh_freshness(response),
                reason=str(response.get("reason") or response.get("summary") or "Mesh organ response observed."),
                candidate_scoped=candidate_linked,
            )
        )
    return [item for item in out if item["strength"] > 0 or item["source_type"] == "ORDERBOOK"]


def _contribution(
    *,
    neuron: str,
    source_type: str,
    supports_side: str,
    confidence: float,
    strength: float,
    source_record_id: str,
    freshness_seconds: int | None,
    reason: str,
    candidate_scoped: bool,
    stale_after_seconds: int = EDGE_TTL_SECONDS,
) -> dict[str, Any]:
    return {
        "neuron": neuron,
        "source_type": source_type,
        "supports_side": supports_side if supports_side in {"YES", "NO", "NEUTRAL", "CONFLICT"} else "NEUTRAL",
        "freshness_seconds": freshness_seconds,
        "stale_after_seconds": stale_after_seconds,
        "confidence": round(max(0.0, min(1.0, float(confidence))), 6),
        "strength": round(max(0.0, min(1.0, float(strength))), 6),
        "evidence_url_or_id": source_record_id,
        "source_record_id": source_record_id,
        "reason": reason,
        "candidate_scoped": candidate_scoped,
    }


def _weighted_score(items: list[dict[str, Any]]) -> float:
    total = 0.0
    for item in items:
        freshness = _freshness_factor(item)
        scope = 1.0 if item.get("candidate_scoped") else 0.82
        total += float(item.get("strength") or 0) * float(item.get("confidence") or 0) * freshness * scope
    return max(0.0, min(1.0, total))


def _weighted_confidence(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return max(0.0, min(1.0, sum(float(item.get("confidence") or 0) for item in items) / len(items)))


def _freshness_factor(item: dict[str, Any]) -> float:
    age = item.get("freshness_seconds")
    ttl = int(item.get("stale_after_seconds") or EDGE_TTL_SECONDS)
    if age is None:
        return 0.65
    try:
        numeric = max(0, int(age))
    except (TypeError, ValueError):
        return 0.65
    if numeric <= ttl:
        return 1.0
    if numeric <= ttl * 2:
        return 0.35
    return 0.0


def _is_stale(item: dict[str, Any]) -> bool:
    age = item.get("freshness_seconds")
    if age is None:
        return False
    try:
        return int(age) > int(item.get("stale_after_seconds") or EDGE_TTL_SECONDS)
    except (TypeError, ValueError):
        return False


def _has_fresh_watch_signal(items: list[dict[str, Any]]) -> bool:
    return any(
        not _is_stale(item)
        and item.get("source_type") in {"NEURON_SIGNAL", "MEMORY_CONTEXT"}
        and item.get("supports_side") in {"NEUTRAL", "YES", "NO"}
        for item in items
    )


def _primary_edge_type(supporting: list[dict[str, Any]], orderbook_items: list[dict[str, Any]]) -> str:
    priority = {
        "NEWS_CONTEXT": "ORDERBOOK_NEWS_DISLOCATION" if orderbook_items else "NEWS_REPRICING_SIGNAL",
        "WHALE_CONTEXT": "WHALE_SIGNAL",
        "PAYOUT_ODDS": "PRICE_PAYOUT_ASYMMETRY",
        "SOCIAL_CONTEXT": "SOCIAL_SIGNAL",
        "CROSS_MARKET_CONTEXT": "CROSS_MARKET_DISLOCATION",
        "NEURON_SIGNAL": "MULTI_FACTOR_MESH_EDGE",
    }
    for item in supporting:
        mapped = priority.get(str(item.get("source_type")))
        if mapped:
            return mapped
    return "ORDERBOOK_LIQUIDITY_SETUP" if orderbook_items else "NO_SOURCE_BACKED_EDGE"


def _required_to_pass(edge_state: str, blocker_code: str | None, missing_identity: list[str]) -> list[str]:
    if missing_identity:
        return [f"Candidate edge thesis must include {field}." for field in missing_identity]
    if edge_state == "EDGE_SUPPORTED":
        return []
    if edge_state == "SOURCE_CONFLICT":
        return ["Resolve or refresh conflicting directional source evidence."]
    if edge_state == "EDGE_STALE":
        return ["Refresh source evidence before Risk can consume edge thesis."]
    if edge_state == "EDGE_SOURCE_ORGANS_UNAVAILABLE":
        return ["Connect at least one candidate-linked directional source organ or resolve missing source configuration/no-data states."]
    if edge_state == "NO_CURRENT_DIRECTIONAL_EDGE":
        return ["Collect current candidate-linked directional evidence; fresh watch-only context is not enough for Risk."]
    if edge_state == "DERIVED_SIGNALS_WATCH_ONLY":
        return ["Wait for independent directional source backing; derived market signals are watch-only."]
    if blocker_code == "EDGE_WEAK":
        return ["Add fresh directional source evidence or wait for stronger confirmation."]
    return ["Collect fresh directional source evidence from news, whale, payout, cross-market, or validated neuron signals."]


def _thesis_summary(edge_state: str, supporting: list[dict[str, Any]], opposing: list[dict[str, Any]], orderbook_items: list[dict[str, Any]], blocker_code: str | None) -> str:
    if edge_state == "EDGE_SUPPORTED":
        names = ", ".join(sorted({item["neuron"] for item in supporting}))
        return f"Source-backed directional edge is supported by {names} with orderbook context."
    if edge_state == "SOURCE_CONFLICT":
        return "Directional sources conflict; Risk must block until conflict is resolved."
    if edge_state == "EDGE_SOURCE_ORGANS_UNAVAILABLE":
        return "Source organs were queried but unavailable, missing config, or connector/data blocked; no source-backed edge can be claimed."
    if edge_state == "DERIVED_SIGNALS_WATCH_ONLY":
        return "Fresh derived/orderbook signals support watch-level monitoring only; no independent directional source backs the candidate side."
    if edge_state == "NO_CURRENT_DIRECTIONAL_EDGE":
        return "Fresh source truth reached Edge, but no current directional source-backed evidence supports the candidate side."
    if orderbook_items and not supporting:
        return "Orderbook supports watch-level context only; no independent directional source backs the candidate side."
    return f"Edge thesis is not risk-usable: {blocker_code or edge_state}."


def _counter_summary(edge_state: str, opposing: list[dict[str, Any]], blocker_code: str | None) -> str:
    if opposing:
        return "Opposing source evidence exists: " + ", ".join(item["source_record_id"] for item in opposing[:5])
    if blocker_code:
        return f"Counter-thesis: {blocker_code} prevents treating this candidate as source-backed edge."
    if edge_state == "EDGE_SUPPORTED":
        return "Counter-thesis: source evidence may already be priced in; Paper must still remain gated by Risk, Exit, and Lifecycle."
    return "No separate counter-thesis available."


def _source_ref(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "neuron": item.get("neuron"),
        "source_type": item.get("source_type"),
        "source_record_id": item.get("source_record_id"),
        "supports_side": item.get("supports_side"),
        "confidence": item.get("confidence"),
        "strength": item.get("strength"),
        "freshness_seconds": item.get("freshness_seconds"),
        "reason": item.get("reason"),
    }


def _thesis_id(candidate_id: str, market_id: str | None, side: str | None, token_id: str | None, contributions: list[dict[str, Any]], edge_state: str) -> str:
    raw = "|".join([candidate_id, str(market_id or ""), str(side or ""), str(token_id or ""), edge_state, ",".join(sorted(str(item.get("source_record_id")) for item in contributions))])
    return f"edge_thesis_{uuid5(NAMESPACE_URL, raw).hex}"


def _market_price(book: dict[str, Any]) -> float | None:
    ask = _decimal_or_none(book.get("best_ask"))
    bid = _decimal_or_none(book.get("best_bid"))
    if ask is not None:
        return float(ask)
    if bid is not None:
        return float(bid)
    return None


def _direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"YES", "NO"}:
        return text
    if text in {"BOTH", "MIXED", "CONFLICT"}:
        return "CONFLICT"
    return "NEUTRAL"


def _signal_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"yes_up", "no_down", "positive"}:
        return "YES"
    if text in {"no_up", "yes_down", "negative"}:
        return "NO"
    if text == "mixed":
        return "CONFLICT"
    return "NEUTRAL"


def _mesh_source_type(response: dict[str, Any]) -> str:
    neuron_type = str(response.get("neuron_type") or "").upper()
    if neuron_type == "ORDERBOOK":
        return "ORDERBOOK"
    if neuron_type == "NEWS":
        return "NEWS_CONTEXT"
    if neuron_type == "WHALE":
        return "WHALE_CONTEXT"
    if neuron_type == "SOCIAL":
        return "SOCIAL_CONTEXT"
    if neuron_type == "MEMORY":
        return "MEMORY_CONTEXT"
    if neuron_type == "CROSS_MARKET":
        return "CROSS_MARKET_CONTEXT"
    if neuron_type == "PAYOUT":
        return "PAYOUT_ODDS"
    if neuron_type == "SIGNAL":
        return "NEURON_SIGNAL"
    if str(response.get("neuron_name") or "") == "source_backed_edge":
        return "MESH_EDGE"
    return "NEURON_SIGNAL"


def _mesh_response_source_id(response: dict[str, Any]) -> str:
    sources = response.get("source_records") or []
    if sources and isinstance(sources[0], dict) and sources[0].get("source_record_id"):
        return str(sources[0]["source_record_id"])
    return f"mesh_response:{response.get('neuron_name') or 'unknown'}:{response.get('created_at') or ''}"


def _mesh_freshness(response: dict[str, Any]) -> int | None:
    value = response.get("freshness_seconds")
    try:
        return max(0, int(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _mesh_response_candidate_linked(response: dict[str, Any]) -> bool:
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    if metadata.get("source_organ"):
        return str(metadata.get("candidate_link_state") or "").startswith("CANDIDATE_LINKED")
    return bool(response.get("candidate_id"))


def _source_organ_status(responses: list[dict[str, Any]]) -> dict[str, Any]:
    source_responses = [
        response
        for response in responses
        if (isinstance(response.get("metadata"), dict) and response["metadata"].get("source_organ"))
        or str(response.get("neuron_type") or "").upper() in {"NEWS", "WHALE", "SOCIAL", "CROSS_MARKET", "MEMORY", "SIGNAL", "PAYOUT", "AI"}
    ]
    unavailable_organs: list[str] = []
    no_data_organs: list[str] = []
    missing_config_organs: list[str] = []
    market_level_only_organs: list[str] = []
    candidate_scoped_organs: list[str] = []
    for response in source_responses:
        name = str(response.get("neuron_name") or "unknown")
        metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
        state = str(metadata.get("source_organ_runtime_state") or response.get("response_state") or "UNKNOWN")
        if state.startswith("UNAVAILABLE") and "NO_DATA" not in state:
            unavailable_organs.append(name)
        if "NO_DATA" in state or response.get("response_state") == "MISSING":
            no_data_organs.append(name)
        if "MISSING_CONFIG" in state:
            missing_config_organs.append(name)
        if state == "ACTIVE_MARKET_LEVEL_ONLY":
            market_level_only_organs.append(name)
        if state == "ACTIVE_CANDIDATE_SCOPED":
            candidate_scoped_organs.append(name)
    all_unavailable = bool(source_responses) and len(unavailable_organs) == len(source_responses)
    return {
        "queried": len(source_responses),
        "unavailable_organs": sorted(set(unavailable_organs)),
        "no_data_organs": sorted(set(no_data_organs)),
        "missing_config_organs": sorted(set(missing_config_organs)),
        "market_level_only_organs": sorted(set(market_level_only_organs)),
        "candidate_scoped_source_organs": sorted(set(candidate_scoped_organs)),
        "missing_source_organs": sorted(set(unavailable_organs + no_data_organs + missing_config_organs)),
        "all_unavailable": all_unavailable,
    }


def _side(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in {"YES", "NO"} else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _float(value: Any, *, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _age_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - value.astimezone(UTC)).total_seconds()))
