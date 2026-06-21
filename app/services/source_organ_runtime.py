from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.full_mesh_contract import mesh_response, unavailable_response
from app.services.full_mesh_registry import FullMeshOrganRegistration


SOURCE_ORGAN_NAMES = {
    "market_movement",
    "news",
    "whale",
    "social",
    "cross_market",
    "market_memory",
    "signal_quality",
    "signal_processing",
    "payout",
    "ai_reasoner",
}

SOURCE_ADAPTERS = {
    "market_movement",
    "news",
    "whale",
    "social",
    "cross_market",
    "market_memory",
    "signal_quality",
    "signal_processing",
    "payout",
}

SOURCE_TYPE_BY_ORGAN = {
    "news": ("NEWS",),
    "whale": ("WHALE",),
    "social": ("SOCIAL",),
    "market_memory": ("MARKET_MEMORY",),
    "ai_reasoner": ("AI_CONTEXT",),
}

DEFAULT_SOURCE_TTL_SECONDS = 3600
NEWS_TTL_SECONDS = 5400
WHALE_TTL_SECONDS = 5400
SIGNAL_TTL_SECONDS = 900
PAYOUT_TTL_SECONDS = 900


def query_source_organ(
    registration: FullMeshOrganRegistration,
    *,
    identity: dict[str, Any],
    connection_factory: DatabaseConnectionFactory,
) -> dict[str, Any]:
    if not connection_factory.enabled:
        return _unavailable(registration, identity, "UNAVAILABLE_NO_CONNECTOR", "Database is not configured for source organ lookup.")
    try:
        with connection_factory.connect() as conn:
            return query_source_organ_with_connection(registration, identity=identity, conn=conn)
    except Exception as exc:
        return mesh_response(
            neuron_name=registration.neuron_name,
            neuron_type=registration.neuron_type,
            identity=identity,
            response_state="ERROR",
            supports_side="UNKNOWN",
            confidence=0.0,
            strength=0.0,
            source_backed=False,
            summary=f"{registration.neuron_name} source organ lookup failed.",
            reason=f"{type(exc).__name__}: {exc}",
            blocker_code=f"{registration.neuron_name.upper()}_UNAVAILABLE_ERROR",
            required_to_pass=[f"Fix {registration.neuron_name} source organ runtime lookup."],
            metadata=_metadata(registration, "UNAVAILABLE_ERROR", error_type=type(exc).__name__),
        )


def query_source_organ_with_connection(
    registration: FullMeshOrganRegistration,
    *,
    identity: dict[str, Any],
    conn: Any,
) -> dict[str, Any]:
    organ = registration.adapter_name or registration.neuron_name
    if organ == "news":
        return _news(registration, identity, conn)
    if organ == "whale":
        return _whale(registration, identity, conn)
    if organ == "social":
        return _social(registration, identity, conn)
    if organ == "cross_market":
        return _cross_market(registration, identity, conn)
    if organ == "market_memory":
        return _market_memory(registration, identity, conn)
    if organ == "market_movement":
        return _market_movement(registration, identity, conn)
    if organ == "signal_quality":
        return _signal(registration, identity, conn, purpose="quality")
    if organ == "signal_processing":
        return _signal(registration, identity, conn, purpose="processing")
    if organ == "payout":
        return _payout(registration, identity, conn)
    return _unavailable(registration, identity, "UNAVAILABLE_NO_CONNECTOR", "No source organ runtime adapter exists.")


def source_organ_status_summary(responses: list[dict[str, Any]]) -> dict[str, Any]:
    source_responses = [item for item in responses if _is_source_response(item)]
    states = [str((item.get("metadata") or {}).get("source_organ_runtime_state") or item.get("response_state") or "UNKNOWN") for item in source_responses]
    by_state: dict[str, int] = {}
    for state in states:
        by_state[state] = by_state.get(state, 0) + 1
    active = [item["neuron_name"] for item in source_responses if str((item.get("metadata") or {}).get("source_organ_runtime_state") or "").startswith("ACTIVE")]
    passive = [item["neuron_name"] for item in source_responses if str((item.get("metadata") or {}).get("source_organ_runtime_state") or "").startswith("PASSIVE")]
    unavailable = [
        item["neuron_name"]
        for item in source_responses
        if str((item.get("metadata") or {}).get("source_organ_runtime_state") or item.get("response_state") or "").startswith("UNAVAILABLE")
        and "NO_DATA" not in str((item.get("metadata") or {}).get("source_organ_runtime_state") or "")
    ]
    missing_config = [
        item["neuron_name"]
        for item in source_responses
        if "MISSING_CONFIG" in str((item.get("metadata") or {}).get("source_organ_runtime_state") or "")
    ]
    no_data = [
        item["neuron_name"]
        for item in source_responses
        if "NO_DATA" in str((item.get("metadata") or {}).get("source_organ_runtime_state") or "")
    ]
    market_level = [
        item["neuron_name"]
        for item in source_responses
        if str((item.get("metadata") or {}).get("source_organ_runtime_state") or "") == "ACTIVE_MARKET_LEVEL_ONLY"
    ]
    candidate_scoped = [
        item["neuron_name"]
        for item in source_responses
        if str((item.get("metadata") or {}).get("source_organ_runtime_state") or "") == "ACTIVE_CANDIDATE_SCOPED"
    ]
    directional = [
        item["neuron_name"]
        for item in source_responses
        if item.get("supports_side") in {"YES", "NO", "CONFLICT"} and float(item.get("strength") or 0) > 0
    ]
    missing_keys: list[str] = []
    for item in source_responses:
        missing_keys.extend(str(key) for key in ((item.get("metadata") or {}).get("missing_config_keys") or []) if key)
    return {
        "source_organs_requested": len(source_responses),
        "source_organs_active": len(active),
        "source_organs_passive": len(passive),
        "source_organs_unavailable": len(unavailable),
        "missing_config_organs": sorted(set(missing_config)),
        "missing_config_keys": sorted(set(missing_keys)),
        "no_data_organs": sorted(set(no_data)),
        "market_level_only_organs": sorted(set(market_level)),
        "candidate_scoped_source_organs": sorted(set(candidate_scoped)),
        "directional_source_organs": sorted(set(directional)),
        "by_state": by_state,
        "organ_statuses": {
            item["neuron_name"]: {
                "state": (item.get("metadata") or {}).get("source_organ_runtime_state") or item.get("response_state"),
                "candidate_link_state": (item.get("metadata") or {}).get("candidate_link_state"),
                "blocker_code": item.get("blocker_code"),
                "source_records": item.get("source_records") or [],
            }
            for item in source_responses
        },
    }


def _news(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any) -> dict[str, Any]:
    context = _provider_context(conn, ("NEWS",))
    market_id = _text(identity.get("market_id"))
    if not market_id:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "NEWS_MISSING_MARKET_ID", "News lookup requires market_id.", context)
    row = _fetchone(
        conn,
        """
        SELECT *
        FROM news_impact_scores
        WHERE market_id=%s
        ORDER BY created_at DESC,id DESC
        LIMIT 1
        """,
        (market_id,),
        table="news_impact_scores",
    )
    if not row:
        link = _fetchone(
            conn,
            """
            SELECT *
            FROM news_market_links
            WHERE market_id=%s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC
            LIMIT 1
            """,
            (market_id,),
            table="news_market_links",
        )
        if link:
            row = dict(link)
            row["_source_table"] = "news_market_links"
            row["_source_id"] = row.get("link_id")
            row.setdefault("impact_id", row.get("link_id"))
            row.setdefault("strength", row.get("link_score"))
            row.setdefault("reason", row.get("link_reason"))
        else:
            return _no_data_or_config(reg, identity, context, "NEWS_NO_DATA", "No news impact/link rows match this candidate market.")
    direction = _direction(row.get("direction"))
    return _directional_row_response(
        reg,
        identity,
        row,
        source_table=str(row.get("_source_table") or ("news_impact_scores" if row.get("impact_id") else "news_market_links")),
        source_id=row.get("_source_id") or row.get("impact_id") or row.get("link_id") or row.get("id"),
        runtime_state="ACTIVE_CANDIDATE_SCOPED" if direction in {"YES", "NO"} else "ACTIVE_MARKET_LEVEL_ONLY",
        candidate_link_state="CANDIDATE_LINKED_MARKET_SIDE" if direction in {"YES", "NO"} else "MARKET_LEVEL_ONLY",
        direction=direction,
        confidence=_float(row.get("confidence"), 0.5),
        strength=_float(row.get("strength") or row.get("link_score"), 0.0) * max(0.0, 1.0 - _float(row.get("already_priced_in"), 0.0)),
        created_at=row.get("updated_at") or row.get("created_at"),
        ttl_seconds=_int(row.get("ttl_seconds"), NEWS_TTL_SECONDS),
        summary="News organ found market-linked directional news evidence." if direction in {"YES", "NO"} else "News organ found market-level news without candidate direction.",
        reason=str(row.get("reason") or row.get("link_reason") or "News source row matched the candidate market."),
        context=context,
    )


def _whale(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any) -> dict[str, Any]:
    context = _provider_context(conn, ("WHALE",))
    market_id = _text(identity.get("market_id"))
    if not market_id:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "WHALE_MISSING_MARKET_ID", "Whale lookup requires market_id.", context)
    row = _fetchone(
        conn,
        """
        SELECT *
        FROM whale_events
        WHERE market_id=%s
        ORDER BY COALESCE(event_time,event_timestamp,created_at) DESC,id DESC
        LIMIT 1
        """,
        (market_id,),
        table="whale_events",
    )
    if not row:
        return _no_data_or_config(reg, identity, context, "WHALE_NO_DATA", "No whale event rows match this candidate market.")
    row_side = _direction(row.get("side") or row.get("side_or_outcome"))
    asset_id = _text(row.get("asset_id"))
    token_id = _text(identity.get("token_id"))
    token_match = bool(asset_id and token_id and asset_id == token_id)
    market_side_link = row_side in {"YES", "NO"}
    state = "ACTIVE_CANDIDATE_SCOPED" if token_match or market_side_link else "ACTIVE_MARKET_LEVEL_ONLY"
    link_state = "CANDIDATE_LINKED_TOKEN" if token_match else "CANDIDATE_LINKED_MARKET_SIDE" if market_side_link else "MARKET_LEVEL_ONLY"
    size = _decimal(row.get("size_usd") or row.get("notional") or row.get("size")) or Decimal("0")
    strength = min(1.0, 0.35 + float(min(size, Decimal("10000")) / Decimal("25000"))) if market_side_link else 0.0
    return _directional_row_response(
        reg,
        identity,
        row,
        source_table="whale_events",
        source_id=row.get("whale_event_id") or row.get("id"),
        runtime_state=state,
        candidate_link_state=link_state,
        direction=row_side,
        confidence=_float(row.get("confidence"), 0.5),
        strength=strength,
        created_at=row.get("event_time") or row.get("event_timestamp") or row.get("created_at"),
        ttl_seconds=WHALE_TTL_SECONDS,
        summary="Whale organ found candidate-linked whale flow." if state == "ACTIVE_CANDIDATE_SCOPED" else "Whale organ found market-level whale flow only.",
        reason=str(row.get("detection_reason_text") or row.get("event_classification") or "Whale event row matched the candidate market."),
        context=context,
    )


def _social(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any) -> dict[str, Any]:
    context = _provider_context(conn, ("SOCIAL",))
    market_id = _text(identity.get("market_id"))
    if not market_id:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "SOCIAL_MISSING_MARKET_ID", "Social lookup requires market_id.", context)
    row = _fetchone(
        conn,
        """
        SELECT *
        FROM social_market_links
        WHERE market_id=%s
        ORDER BY created_at DESC,id DESC
        LIMIT 1
        """,
        (market_id,),
        table="social_market_links",
    )
    if not row:
        row = _fetchone(
            conn,
            """
            SELECT *
            FROM social_hype_scores
            WHERE market_id=%s
            ORDER BY computed_at DESC,id DESC
            LIMIT 1
            """,
            (market_id,),
            table="social_hype_scores",
        )
    if not row:
        return _no_data_or_config(reg, identity, context, "SOCIAL_NO_DATA", "No social hype/link rows match this candidate market.")
    direction = _direction(row.get("sentiment_direction"))
    return _directional_row_response(
        reg,
        identity,
        row,
        source_table="social_market_links" if row.get("social_link_id") else "social_hype_scores",
        source_id=row.get("social_link_id") or row.get("hype_id") or row.get("id"),
        runtime_state="ACTIVE_CANDIDATE_SCOPED" if direction in {"YES", "NO"} else "ACTIVE_MARKET_LEVEL_ONLY",
        candidate_link_state="CANDIDATE_LINKED_MARKET_SIDE" if direction in {"YES", "NO"} else "MARKET_LEVEL_ONLY",
        direction=direction,
        confidence=_float(row.get("confidence") or row.get("sentiment_confidence"), 0.5),
        strength=_float(row.get("link_score") or row.get("hype_pressure") or row.get("narrative_strength"), 0.0),
        created_at=row.get("computed_at") or row.get("created_at"),
        ttl_seconds=NEWS_TTL_SECONDS,
        summary="Social organ found market-linked social evidence.",
        reason=str(row.get("link_reason") or "Social source row matched the candidate market."),
        context=context,
    )


def _cross_market(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any) -> dict[str, Any]:
    tables = ["external_market_prices", "cross_market_discrepancies", "external_odds"]
    existing = [name for name in tables if _table_exists(conn, name)]
    if not existing:
        return _unavailable(reg, identity, "UNAVAILABLE_NO_CONNECTOR", "No cross-market connector/table exists in this repository runtime.")
    return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "CROSS_MARKET_NO_DATA", f"Cross-market tables exist ({', '.join(existing)}) but no candidate linker is available yet.", {"existing_tables": existing})


def _market_memory(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any) -> dict[str, Any]:
    context = _provider_context(conn, ("MARKET_MEMORY",))
    market_id = _text(identity.get("market_id"))
    if not market_id:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "MEMORY_MISSING_MARKET_ID", "Market memory lookup requires market_id.", context)
    row = _fetchone(conn, "SELECT * FROM market_memory_v2 WHERE market_id=%s ORDER BY COALESCE(updated_at,last_updated_at,last_seen_at) DESC,id DESC LIMIT 1", (market_id,), table="market_memory_v2")
    if not row:
        return _no_data_or_config(reg, identity, context, "MEMORY_NO_DATA", "No market memory rows match this candidate market.")
    strength = max(_float(row.get("news_reaction_score"), 0.0), _float(row.get("social_reaction_score"), 0.0), _float(row.get("whale_reaction_score"), 0.0))
    return _directional_row_response(
        reg,
        identity,
        row,
        source_table="market_memory_v2",
        source_id=row.get("id") or row.get("market_id"),
        runtime_state="ACTIVE_MARKET_LEVEL_ONLY",
        candidate_link_state="MARKET_LEVEL_ONLY",
        direction="NEUTRAL",
        confidence=_float(row.get("memory_confidence"), 0.0),
        strength=strength,
        created_at=row.get("updated_at") or row.get("last_updated_at") or row.get("last_seen_at"),
        ttl_seconds=86400,
        summary="Market memory is available for this market but is not directional candidate evidence.",
        reason=str(row.get("memory_status") or "Market memory row matched market_id."),
        context=context,
    )


def _market_movement(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any) -> dict[str, Any]:
    market_id = _text(identity.get("market_id"))
    token_id = _text(identity.get("token_id"))
    if not market_id:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "MARKET_MOVEMENT_MISSING_MARKET_ID", "Market movement lookup requires market_id.", {})
    row = _fetchone(
        conn,
        """
        SELECT *
        FROM market_technical_signals
        WHERE market_id=%s
        ORDER BY ts DESC,created_at DESC,id DESC
        LIMIT 1
        """,
        (market_id,),
        table="market_technical_signals",
    )
    if not row:
        query = """
            SELECT *
            FROM orderbook_signals
            WHERE market_id=%s
            """
        params: list[Any] = [market_id]
        if token_id:
            query += " AND token_id=%s"
            params.append(token_id)
        query += """
            ORDER BY ts DESC,created_at DESC,id DESC
            LIMIT 1
            """
        row = _fetchone(
            conn,
            query,
            tuple(params),
            table="orderbook_signals",
        )
    if not row:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "MARKET_MOVEMENT_NO_DATA", "No market movement/technical signal rows match this candidate.", {})
    direction = _direction(row.get("trend_direction"))
    return _directional_row_response(
        reg,
        identity,
        row,
        source_table="market_technical_signals" if row.get("technical_score") is not None else "orderbook_signals",
        source_id=row.get("id"),
        runtime_state="ACTIVE_CANDIDATE_SCOPED" if row.get("token_id") and str(row.get("token_id")) == str(token_id) else "ACTIVE_MARKET_LEVEL_ONLY",
        candidate_link_state="CANDIDATE_LINKED_TOKEN" if row.get("token_id") and str(row.get("token_id")) == str(token_id) else "MARKET_LEVEL_ONLY",
        direction=direction,
        confidence=_float(row.get("data_completeness_score"), 0.5),
        strength=_float(row.get("trend_strength") or row.get("technical_score") or row.get("orderbook_quality_score"), 0.0),
        created_at=row.get("ts") or row.get("created_at"),
        ttl_seconds=SIGNAL_TTL_SECONDS,
        summary="Market movement organ found technical/orderbook movement evidence.",
        reason=str(row.get("market_regime") or row.get("block_reason") or "Movement source row matched market_id."),
        context={},
    )


def _signal(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any, *, purpose: str) -> dict[str, Any]:
    market_id = _text(identity.get("market_id"))
    side = _side(identity.get("side"))
    if not market_id:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "SIGNAL_MISSING_MARKET_ID", "Signal lookup requires market_id.", {})
    row = _fetchone(
        conn,
        """
        SELECT s.signal_id, s.neuron, s.event_type, s.source_name, s.market_id, s.correlation_id,
               s.raw_direction, s.strength, s.confidence, s.source_reliability,
               s.freshness_seconds, s.status, s.evidence_json, s.raw_payload_ref,
               s.ttl_seconds, s.expires_at, s.stale_after_seconds, s.created_at, s.updated_at,
               b.id AS binding_id, b.matched_side, b.side_confidence, b.side_evidence_json,
               b.side_rejected_reason, q.quality_score, q.quality_status, q.can_feed_brain, q.can_feed_paper, q.is_stale AS quality_is_stale
        FROM neuron_signals s
        LEFT JOIN LATERAL (
            SELECT *
            FROM neuron_signal_bindings b
            WHERE b.signal_id=s.signal_id
            ORDER BY b.created_at DESC,b.id DESC
            LIMIT 1
        ) b ON true
        LEFT JOIN LATERAL (
            SELECT *
            FROM signal_quality_evaluations q
            WHERE q.signal_id=s.signal_id
            ORDER BY q.evaluated_at DESC,q.id DESC
            LIMIT 1
        ) q ON true
        WHERE (s.market_id=%s OR b.market_id=%s)
        ORDER BY s.created_at DESC,s.id DESC
        LIMIT 1
        """,
        (market_id, market_id),
        table="neuron_signals",
    )
    if not row:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "SIGNAL_NO_DATA", "No neuron signal rows match this candidate market.", {})
    raw_direction = _signal_direction(row.get("raw_direction"))
    matched_side = _side(row.get("matched_side"))
    direction = matched_side or raw_direction
    candidate_link = "CANDIDATE_LINKED_MARKET_SIDE" if direction in {"YES", "NO"} else "MARKET_LEVEL_ONLY"
    state = "ACTIVE_CANDIDATE_SCOPED" if candidate_link.startswith("CANDIDATE_LINKED") else "ACTIVE_MARKET_LEVEL_ONLY"
    confidence = max(_float(row.get("confidence"), 0.0), _float(row.get("side_confidence"), 0.0), _float(row.get("quality_score"), 0.0))
    strength = _float(row.get("strength"), 0.0)
    if purpose == "quality" and row.get("quality_score") is not None:
        strength = min(strength, _float(row.get("quality_score"), 0.0)) if strength else _float(row.get("quality_score"), 0.0)
    return _directional_row_response(
        reg,
        identity,
        row,
        source_table="neuron_signals",
        source_id=row.get("signal_id"),
        runtime_state=state,
        candidate_link_state=candidate_link,
        direction=direction,
        confidence=confidence,
        strength=strength,
        created_at=row.get("created_at"),
        ttl_seconds=_int(row.get("stale_after_seconds") or row.get("ttl_seconds"), SIGNAL_TTL_SECONDS),
        summary=f"Signal organ found {row.get('neuron') or 'unknown'} signal for candidate market.",
        reason=str((_dict(row.get("evidence_json")).get("reason")) or row.get("event_type") or "Neuron signal matched market_id."),
        context={"signal_purpose": purpose, "binding_id": row.get("binding_id"), "quality_status": row.get("quality_status")},
    )


def _payout(reg: FullMeshOrganRegistration, identity: dict[str, Any], conn: Any) -> dict[str, Any]:
    candidate_id = _text(identity.get("candidate_id"))
    market_id = _text(identity.get("market_id"))
    side = _side(identity.get("side"))
    token_id = _text(identity.get("token_id"))
    row = None
    if candidate_id:
        row = _fetchone(
            conn,
            """
            SELECT *
            FROM payout_odds_evaluations
            WHERE subject_id=%s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC
            LIMIT 1
            """,
            (candidate_id,),
            table="payout_odds_evaluations",
        )
    if not row and market_id:
        query = """
            SELECT *
            FROM payout_odds_evaluations
            WHERE market_id=%s
            """
        params: list[Any] = [market_id]
        if side:
            query += " AND side=%s"
            params.append(side)
        if token_id:
            query += " AND token_id=%s"
            params.append(token_id)
        query += """
            ORDER BY created_at DESC,id DESC
            LIMIT 1
            """
        row = _fetchone(
            conn,
            query,
            tuple(params),
            table="payout_odds_evaluations",
        )
    if not row:
        return _missing(reg, identity, "UNAVAILABLE_NO_DATA", "PAYOUT_NO_DATA", "No payout odds evaluation matches this candidate.", {})
    risk_reward = _decimal(row.get("risk_reward"))
    strength = 0.0
    if risk_reward is not None and risk_reward >= Decimal("1.0"):
        strength = float(min(Decimal("1"), Decimal("0.35") + min(risk_reward - Decimal("1.0"), Decimal("1.0")) * Decimal("0.25")))
    link_state = "CANDIDATE_LINKED_TOKEN" if token_id and str(row.get("token_id") or "") == token_id else "CANDIDATE_LINKED_MARKET_SIDE"
    return _directional_row_response(
        reg,
        identity,
        row,
        source_table="payout_odds_evaluations",
        source_id=row.get("evaluation_id") or row.get("id"),
        runtime_state="ACTIVE_CANDIDATE_SCOPED",
        candidate_link_state=link_state,
        direction=side or "NEUTRAL",
        confidence=0.68,
        strength=strength,
        created_at=row.get("updated_at") or row.get("created_at"),
        ttl_seconds=PAYOUT_TTL_SECONDS,
        summary="Payout organ found candidate-specific payout odds evidence.",
        reason="Payout odds are observational and do not invent fair probability.",
        context={"risk_reward": float(risk_reward) if risk_reward is not None else None, "fair_probability_present": row.get("fair_probability") is not None},
    )


def _directional_row_response(
    reg: FullMeshOrganRegistration,
    identity: dict[str, Any],
    row: dict[str, Any],
    *,
    source_table: str,
    source_id: Any,
    runtime_state: str,
    candidate_link_state: str,
    direction: str,
    confidence: float,
    strength: float,
    created_at: Any,
    ttl_seconds: int,
    summary: str,
    reason: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    side = _side(identity.get("side"))
    age = _age_seconds(created_at)
    stale = age is not None and age > ttl_seconds
    if stale:
        response_state = "STALE"
    elif direction in {"YES", "NO"} and side and direction != side:
        response_state = "OPPOSED"
    elif direction in {"YES", "NO"} and side and direction == side and strength > 0:
        response_state = "SUPPORTED"
    elif direction in {"YES", "NO"}:
        response_state = "WATCH"
    elif direction == "CONFLICT":
        response_state = "BLOCKED"
    else:
        response_state = "NEUTRAL"
    if runtime_state == "ACTIVE_MARKET_LEVEL_ONLY" and candidate_link_state == "MARKET_LEVEL_ONLY":
        strength = 0.0
    metadata = _metadata(
        reg,
        runtime_state,
        candidate_link_state=candidate_link_state,
        missing_config_keys=context.get("missing_config_keys") or [],
        directional_source=direction in {"YES", "NO", "CONFLICT"} and strength > 0,
        ttl_seconds=ttl_seconds,
        provider_context=context,
    )
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state=response_state,
        supports_side=direction,
        confidence=confidence,
        strength=strength,
        freshness_seconds=age,
        source_backed=True,
        summary=summary,
        reason=reason,
        blocker_code="SOURCE_STALE" if stale else None,
        required_to_pass=["Refresh source evidence."] if stale else [],
        source_records=[{"source_type": source_table, "source_record_id": str(source_id) if source_id is not None else None}],
        metadata=metadata,
    )


def _no_data_or_config(reg: FullMeshOrganRegistration, identity: dict[str, Any], context: dict[str, Any], blocker: str, reason: str) -> dict[str, Any]:
    if context.get("provider_ready") is False and context.get("missing_config_keys"):
        return _unavailable(
            reg,
            identity,
            "UNAVAILABLE_MISSING_CONFIG",
            f"{reason} Required source config is missing.",
            blocker_code=f"{reg.neuron_name.upper()}_MISSING_CONFIG",
            required=[f"Configure {key} or keep {reg.neuron_name} unavailable." for key in context.get("missing_config_keys") or []],
            context=context,
        )
    return _missing(reg, identity, "UNAVAILABLE_NO_DATA", blocker, reason, context)


def _missing(reg: FullMeshOrganRegistration, identity: dict[str, Any], runtime_state: str, blocker: str, reason: str, context: dict[str, Any]) -> dict[str, Any]:
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state="MISSING",
        supports_side="UNKNOWN",
        confidence=0.0,
        strength=0.0,
        source_backed=False,
        summary=reason,
        reason=reason,
        blocker_code=blocker,
        required_to_pass=[reason],
        source_records=[],
        metadata=_metadata(reg, runtime_state, provider_context=context, missing_config_keys=context.get("missing_config_keys") or []),
    )


def _unavailable(
    reg: FullMeshOrganRegistration,
    identity: dict[str, Any],
    runtime_state: str,
    reason: str,
    *,
    blocker_code: str | None = None,
    required: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return unavailable_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        reason=reason,
        blocker_code=blocker_code or f"{reg.neuron_name.upper()}_{runtime_state}",
        required_to_pass=required or [reason],
    ) | {"metadata": _metadata(reg, runtime_state, provider_context=context or {}, missing_config_keys=(context or {}).get("missing_config_keys") or [])}


def _metadata(reg: FullMeshOrganRegistration, runtime_state: str, **extra: Any) -> dict[str, Any]:
    return {
        "source_organ": True,
        "source_organ_runtime_state": runtime_state,
        "adapter_status": "RUNTIME_CONNECTED" if runtime_state.startswith("ACTIVE") or runtime_state in {"UNAVAILABLE_NO_DATA", "UNAVAILABLE_MISSING_CONFIG"} else runtime_state,
        "organ_name": reg.neuron_name,
        **extra,
    }


def _provider_context(conn: Any, source_types: tuple[str, ...]) -> dict[str, Any]:
    if not _table_exists(conn, "intelligence_source_registry"):
        return {"provider_ready": None, "registry_rows": [], "missing_config_keys": []}
    rows = _fetchall(
        conn,
        """
        SELECT source_id, source_type, provider_name, requires_api_key, required_env_vars,
               optional_env_vars, status, health_status, enabled_by_default, target_tables_json
        FROM intelligence_source_registry
        WHERE source_type = ANY(%s)
        ORDER BY source_id
        """,
        (list(source_types),),
    )
    missing_keys: set[str] = set()
    if _table_exists(conn, "intelligence_source_credentials_status"):
        cred_rows = _fetchall(
            conn,
            """
            SELECT source_id, env_var, required, present, validity_status
            FROM intelligence_source_credentials_status
            WHERE source_id = ANY(%s)
            """,
            ([str(row.get("source_id")) for row in rows],),
        )
        for cred in cred_rows:
            if cred.get("required") and not cred.get("present"):
                missing_keys.add(str(cred.get("env_var")))
    for row in rows:
        if str(row.get("status") or "").upper() == "MISSING_CREDENTIALS":
            for key in row.get("required_env_vars") or []:
                missing_keys.add(str(key))
    ready = any(str(row.get("status") or "").upper() in {"READY", "READY_NO_KEY"} for row in rows)
    return {
        "provider_ready": ready if rows else None,
        "missing_config_keys": sorted(missing_keys),
        "registry_rows": [
            {
                "source_id": row.get("source_id"),
                "status": row.get("status"),
                "health_status": row.get("health_status"),
                "required_env_vars": row.get("required_env_vars") or [],
                "optional_env_vars": row.get("optional_env_vars") or [],
                "target_tables_json": row.get("target_tables_json") or [],
            }
            for row in rows
        ],
    }


def _is_source_response(item: dict[str, Any]) -> bool:
    return bool((item.get("metadata") or {}).get("source_organ")) or str(item.get("neuron_name") or "") in SOURCE_ORGAN_NAMES


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = (), *, table: str | None = None) -> dict[str, Any] | None:
    if table and not _table_exists(conn, table):
        return None
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"YES", "NO"}:
        return text
    if text in {"MIXED", "BOTH", "CONFLICT"}:
        return "CONFLICT"
    if text in {"POSITIVE", "UP", "BULLISH"}:
        return "YES"
    if text in {"NEGATIVE", "DOWN", "BEARISH"}:
        return "NO"
    return "NEUTRAL"


def _signal_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"yes_up", "no_down", "positive", "bullish", "up"}:
        return "YES"
    if text in {"no_up", "yes_down", "negative", "bearish", "down"}:
        return "NO"
    if text in {"mixed", "both", "conflict"}:
        return "CONFLICT"
    return "NEUTRAL"


def _side(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in {"YES", "NO"} else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
