from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.full_mesh_contract import mesh_response, unavailable_response
from app.services.full_mesh_registry import FullMeshOrganRegistration
from app.services.source_organ_runtime import SOURCE_ADAPTERS, query_source_organ


def query_organ(
    registration: FullMeshOrganRegistration,
    *,
    identity: dict[str, Any],
    bundle: dict[str, Any],
    edge: dict[str, Any] | None = None,
    actionability: dict[str, Any] | None = None,
    connection_factory: DatabaseConnectionFactory | None = None,
) -> dict[str, Any]:
    adapter = registration.adapter_name or registration.neuron_name
    try:
        if adapter == "candidate":
            return _candidate(registration, identity, bundle)
        if adapter == "candidate_event_correlation":
            return _candidate_event_correlation(registration, identity, bundle)
        if adapter in {"orderbook", "candidate_price_path"}:
            return _orderbook(registration, identity, bundle, candidate_price_path=adapter == "candidate_price_path")
        if adapter == "liquidity":
            return _opinion(registration, identity, bundle, "liquidity")
        if adapter == "risk":
            return _risk(registration, identity, bundle, edge)
        if adapter == "exit":
            return _opinion(registration, identity, bundle, "exit")
        if adapter == "capital":
            return _opinion(registration, identity, bundle, "capital")
        if adapter == "lifecycle":
            return _opinion(registration, identity, bundle, "lifecycle")
        if adapter == "coordinator":
            return _coordinator(registration, identity, bundle)
        if adapter == "source_backed_edge":
            return _source_backed_edge(registration, identity, edge)
        if adapter == "paper_actionability":
            return _paper_actionability(registration, identity, actionability)
        if adapter == "ai_reasoner":
            return _ai_reasoner(registration, identity, edge)
        if adapter in SOURCE_ADAPTERS and connection_factory is not None:
            return query_source_organ(registration, identity=identity, connection_factory=connection_factory)
        if registration.passive_only or registration.availability != "AVAILABLE":
            return unavailable_response(
                neuron_name=registration.neuron_name,
                neuron_type=registration.neuron_type,
                identity=identity,
                reason=f"{registration.neuron_name} is registered but {registration.availability.lower()} for candidate-scoped inquiry.",
                blocker_code=f"{registration.neuron_name.upper()}_{registration.availability}",
            )
        return unavailable_response(neuron_name=registration.neuron_name, neuron_type=registration.neuron_type, identity=identity, reason="No Mesh adapter is implemented for this organ.")
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
            summary=f"{registration.neuron_name} adapter failed.",
            reason=f"{type(exc).__name__}: {exc}",
            blocker_code="ORGAN_ADAPTER_ERROR",
            required_to_pass=[f"Fix {registration.neuron_name} Mesh adapter error."],
        )


def _candidate(reg: FullMeshOrganRegistration, identity: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in ("candidate_id", "market_id", "side", "token_id") if not identity.get(key)]
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state="SUPPORTED" if not missing else "MISSING",
        supports_side=str(identity.get("side") or "UNKNOWN"),
        confidence=0.88 if not missing else 0.2,
        strength=0.7 if not missing else 0.0,
        source_backed=not missing,
        summary="Candidate identity is complete." if not missing else "Candidate identity is incomplete.",
        reason="Candidate-scoped bundle identity was used.",
        blocker_code=None if not missing else "CANDIDATE_IDENTITY_INCOMPLETE",
        required_to_pass=[f"Provide candidate {field}." for field in missing],
        source_records=[_source_ref("mesh_bundle", bundle.get("bundle_id") or bundle.get("correlation_id"))],
    )


def _candidate_event_correlation(reg: FullMeshOrganRegistration, identity: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    state = str(bundle.get("candidate_event_link_state") or "UNKNOWN")
    scoped = bundle.get("candidate_event_actionability_scope") == "CANDIDATE_SCOPED" and bundle.get("correlation_confidence") == "HIGH"
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state="SUPPORTED" if scoped else "BLOCKED",
        supports_side=str(identity.get("side") or "UNKNOWN"),
        confidence=0.92 if scoped else 0.25,
        strength=0.7 if scoped else 0.0,
        source_backed=scoped,
        summary=f"Candidate/event link state is {state}.",
        reason=f"Actionability scope={bundle.get('candidate_event_actionability_scope')} confidence={bundle.get('correlation_confidence')}.",
        blocker_code=None if scoped else state,
        required_to_pass=[] if scoped else ["Event must be candidate-scoped with HIGH correlation confidence."],
        source_records=[_source_ref("event_log", bundle.get("event_id"))],
    )


def _orderbook(reg: FullMeshOrganRegistration, identity: dict[str, Any], bundle: dict[str, Any], *, candidate_price_path: bool) -> dict[str, Any]:
    orderbook = bundle.get("orderbook") or {}
    fresh = str(orderbook.get("freshness_state") or "").upper() in {"FRESH", "TRUSTED_FRESH"} or str(orderbook.get("trusted_state") or "").upper() in {"TRUSTED_FRESH", "OK"}
    response_state = "WATCH" if fresh else "STALE"
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state=response_state,
        supports_side=str(identity.get("side") or "UNKNOWN"),
        confidence=0.72 if fresh else 0.25,
        strength=0.3 if fresh else 0.0,
        freshness_seconds=_int_or_none(orderbook.get("age_seconds")),
        source_backed=fresh,
        summary=f"Orderbook evidence is {orderbook.get('freshness_state') or orderbook.get('trusted_state') or 'UNKNOWN'}.",
        reason="Orderbook provides watch-level price context only.",
        blocker_code=None if fresh else "ORDERBOOK_STALE_OR_MISSING",
        required_to_pass=[] if fresh else ["Refresh candidate-scoped trusted orderbook."],
        source_records=[_source_ref("orderbook_snapshot", orderbook.get("snapshot_id"))],
        metadata={"best_bid": orderbook.get("best_bid"), "best_ask": orderbook.get("best_ask"), "spread": orderbook.get("spread"), "candidate_price_path": candidate_price_path},
    )


def _opinion(reg: FullMeshOrganRegistration, identity: dict[str, Any], bundle: dict[str, Any], name: str) -> dict[str, Any]:
    opinions = bundle.get("opinions") or {}
    opinion = opinions.get(name) or {}
    state = str(opinion.get("state") or opinion.get(f"{name}_opinion_state") or "UNKNOWN")
    blockers = list(opinion.get("blockers") or [])
    response_state = "BLOCKED" if blockers or "BLOCKED" in state or "DENIED" in state else "SUPPORTED" if state not in {"MISSING", "UNKNOWN", "STALE"} else state if state in {"MISSING", "STALE"} else "NEUTRAL"
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state=response_state,
        supports_side=str(identity.get("side") or "UNKNOWN") if response_state == "SUPPORTED" else "UNKNOWN",
        confidence=0.72 if response_state == "SUPPORTED" else 0.4 if response_state == "BLOCKED" else 0.2,
        strength=0.5 if response_state == "SUPPORTED" else 0.0,
        source_backed=bool(opinion),
        summary=str(opinion.get("summary") or f"{name} opinion state is {state}."),
        reason=str(opinion.get("reason") or opinion.get("summary") or state),
        blocker_code=blockers[0] if blockers else None,
        required_to_pass=[f"{name} blocker must clear."] if blockers else [],
        source_records=[_source_ref("brain_output", opinion.get("brain_output_id") or opinion.get("decision_source"))],
        metadata=opinion,
    )


def _risk(reg: FullMeshOrganRegistration, identity: dict[str, Any], bundle: dict[str, Any], edge: dict[str, Any] | None) -> dict[str, Any]:
    edge = edge or {}
    if edge and edge.get("risk_usable") is True:
        state = "SUPPORTED"
        blocker = None
        required: list[str] = []
    elif edge:
        state = "BLOCKED" if edge.get("blocker_code") else "WATCH"
        blocker = str(edge.get("blocker_code") or edge.get("edge_state") or "EDGE_NOT_RISK_USABLE")
        required = list(edge.get("required_to_pass") or ["Risk requires source-backed edge thesis."])
    else:
        state = "MISSING"
        blocker = "EDGE_THESIS_MISSING"
        required = ["Build source-backed Edge Thesis."]
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state=state,
        supports_side=str(identity.get("side") or "UNKNOWN") if edge.get("risk_usable") is True else "UNKNOWN",
        confidence=float(edge.get("edge_score") or 0.0) if edge else 0.0,
        strength=float(edge.get("edge_score") or 0.0) if edge else 0.0,
        source_backed=edge.get("source_backed") is True,
        summary=edge.get("operator_summary") or "Risk consumes Edge Thesis.",
        reason=edge.get("ai_thesis") or "Risk requires source-backed edge.",
        blocker_code=blocker,
        required_to_pass=required,
        source_records=list(edge.get("source_records") or []),
        metadata={"edge_state": edge.get("edge_state"), "risk_usable": edge.get("risk_usable"), "edge_thesis_id": edge.get("edge_thesis_id")},
    )


def _source_backed_edge(reg: FullMeshOrganRegistration, identity: dict[str, Any], edge: dict[str, Any] | None) -> dict[str, Any]:
    edge = edge or {}
    if not edge:
        return unavailable_response(neuron_name=reg.neuron_name, neuron_type=reg.neuron_type, identity=identity, reason="No Edge Thesis exists for this candidate.", blocker_code="EDGE_THESIS_MISSING", required_to_pass=["Build Edge Thesis from Mesh inquiry responses."])
    state = "SUPPORTED" if edge.get("risk_usable") is True else "WATCH" if edge.get("edge_state") == "EDGE_WATCH" else "BLOCKED"
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state=state,
        supports_side=str(identity.get("side") or "UNKNOWN") if edge.get("source_backed") else "UNKNOWN",
        confidence=float(edge.get("edge_score") or 0.0),
        strength=float(edge.get("edge_score") or 0.0),
        source_backed=edge.get("source_backed") is True,
        summary=edge.get("ai_thesis") or "Edge Thesis is available.",
        reason=edge.get("blocker_code") or edge.get("edge_state") or "EDGE_UNKNOWN",
        blocker_code=edge.get("blocker_code"),
        required_to_pass=list(edge.get("required_to_pass") or []),
        source_records=list(edge.get("source_records") or []),
        metadata=edge,
    )


def _coordinator(reg: FullMeshOrganRegistration, identity: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    coordinator = bundle.get("coordinator") or {}
    decision = str(coordinator.get("decision") or "UNKNOWN")
    blocked = decision in {"LIFECYCLE_BLOCKED", "CAPITAL_BLOCKED", "PRICE_BLOCKED", "CONFLICT", "NO_ACTION"}
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state="BLOCKED" if blocked else "SUPPORTED" if decision == "PRICE_READY" else "WATCH",
        supports_side=str(identity.get("side") or "UNKNOWN") if decision == "PRICE_READY" else "UNKNOWN",
        confidence=0.7,
        strength=0.5 if decision == "PRICE_READY" else 0.0,
        source_backed=bool(coordinator),
        summary=f"Coordinator decision is {decision}.",
        reason=str(coordinator.get("reason") or decision),
        blocker_code=decision if blocked else None,
        required_to_pass=list(coordinator.get("required_to_progress") or []),
        source_records=[_source_ref("coordinator_decision", coordinator.get("decision_id"))],
        metadata=coordinator,
    )


def _paper_actionability(reg: FullMeshOrganRegistration, identity: dict[str, Any], actionability: dict[str, Any] | None) -> dict[str, Any]:
    actionability = actionability or {}
    state = str(actionability.get("candidate_paper_actionability_state") or "UNKNOWN")
    supported = state in {"ACTIONABLE_SMALL_PAPER", "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"}
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state="SUPPORTED" if supported else "BLOCKED" if state.startswith("BLOCKED") else "WATCH",
        supports_side=str(identity.get("side") or "UNKNOWN") if supported else "UNKNOWN",
        confidence=0.8 if supported else 0.4,
        strength=0.6 if supported else 0.0,
        source_backed=bool(actionability),
        summary=f"Paper actionability state is {state}.",
        reason=str(actionability.get("operator_summary") or state),
        blocker_code=(actionability.get("blockers") or [None])[0],
        required_to_pass=list(actionability.get("required_to_pass") or []),
        source_records=[_source_ref("mesh_bundle", actionability.get("mesh_bundle_id"))],
        metadata=actionability,
    )


def _ai_reasoner(reg: FullMeshOrganRegistration, identity: dict[str, Any], edge: dict[str, Any] | None) -> dict[str, Any]:
    edge = edge or {}
    status = str(edge.get("ai_review_status") or "UNAVAILABLE")
    return mesh_response(
        neuron_name=reg.neuron_name,
        neuron_type=reg.neuron_type,
        identity=identity,
        response_state="NEUTRAL" if status not in {"UNAVAILABLE", "REJECTED"} else "UNAVAILABLE",
        supports_side="UNKNOWN",
        confidence=0.0,
        strength=0.0,
        source_backed=False,
        summary=str(edge.get("ai_thesis") or "AI reasoner unavailable; deterministic fallback used."),
        reason=f"AI review status={status}",
        blocker_code=None if status not in {"UNAVAILABLE", "REJECTED"} else f"AI_REVIEW_{status}",
        required_to_pass=[] if status not in {"UNAVAILABLE", "REJECTED"} else ["Configure a valid AI reasoner or keep deterministic fallback explicit."],
        source_records=[],
        metadata={"ai_review_model": edge.get("ai_review_model"), "ai_review_status": status},
    )


def _source_ref(source_type: str, source_id: Any) -> dict[str, Any]:
    return {"source_type": source_type, "source_record_id": str(source_id) if source_id else None}


def _int_or_none(value: Any) -> int | None:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None
