from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.db.connection import DatabaseConnectionFactory
from app.services.full_mesh_contract import identity_from_bundle
from app.services.full_mesh_registry import full_mesh_registry, validate_decision_critical_coverage
from app.services.mesh_organ_adapters import query_organ
from app.services.source_organ_runtime import source_organ_status_summary
from app.services.source_backed_edge_engine import build_edge_thesis_from_mesh_responses


class FullMeshInquiryOrchestrator:
    """Read-only Mesh inquiry orchestrator for candidate-scoped evidence rooms."""

    def __init__(self, *, registry: list[Any] | None = None, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._registry = registry or full_mesh_registry()
        self._factory = connection_factory

    def build_session(self, bundle: dict[str, Any], *, edge: dict[str, Any] | None = None, actionability: dict[str, Any] | None = None) -> dict[str, Any]:
        identity = identity_from_bundle(bundle)
        responses = [
            query_organ(reg, identity=identity, bundle=bundle, edge=edge, actionability=actionability, connection_factory=self._factory)
            for reg in self._registry
            if reg.safe_for_pre_paper_inquiry
        ]
        response_counts = Counter(response["response_state"] for response in responses)
        source_summary = source_organ_status_summary(responses)
        supporting = sorted({response["neuron_name"] for response in responses if response["response_state"] == "SUPPORTED" and response["supports_side"] == identity.get("side")})
        opposing = sorted({response["neuron_name"] for response in responses if response["supports_side"] in {"YES", "NO"} and response["supports_side"] != identity.get("side")})
        neutral = sorted({response["neuron_name"] for response in responses if response["response_state"] in {"NEUTRAL", "WATCH"}})
        missing = sorted({response["neuron_name"] for response in responses if response["response_state"] in {"MISSING", "UNAVAILABLE", "ERROR"}})
        inquiry_thesis = build_edge_thesis_from_mesh_responses(identity, responses)
        canonical_edge = edge or inquiry_thesis
        actionability_state = str((actionability or {}).get("candidate_paper_actionability_state") or "UNKNOWN")
        risk_result = str(canonical_edge.get("risk_decision") or canonical_edge.get("edge_state") or "UNKNOWN")
        lifecycle_result = str(((bundle.get("opinions") or {}).get("lifecycle") or {}).get("lifecycle_opinion_state") or ((bundle.get("opinions") or {}).get("lifecycle") or {}).get("state") or "UNKNOWN")
        final_blocker = _final_blocker(actionability, canonical_edge, responses)
        inquiry_state = _inquiry_state(responses, canonical_edge, actionability_state)
        return {
            "mesh_session_id": _session_id(identity, bundle),
            "candidate_id": identity.get("candidate_id"),
            "market_id": identity.get("market_id"),
            "condition_id": identity.get("condition_id"),
            "side": identity.get("side"),
            "token_id": identity.get("token_id"),
            "correlation_id": identity.get("correlation_id"),
            "event_id": identity.get("event_id"),
            "inquiry_state": inquiry_state,
            "neurons_requested": len(responses),
            "neurons_responded": sum(1 for response in responses if response["response_state"] not in {"UNAVAILABLE", "ERROR"}),
            "neurons_unavailable": response_counts.get("UNAVAILABLE", 0),
            "neurons_stale": response_counts.get("STALE", 0),
            "neurons_error": response_counts.get("ERROR", 0),
            "supporting_neurons": supporting,
            "opposing_neurons": opposing,
            "neutral_neurons": neutral,
            "missing_neurons": missing,
            "responses": responses,
            "source_organ_status_summary": source_summary,
            "source_organs_active": source_summary["source_organs_active"],
            "source_organs_passive": source_summary["source_organs_passive"],
            "source_organs_unavailable": source_summary["source_organs_unavailable"],
            "missing_config_organs": source_summary["missing_config_organs"],
            "no_data_organs": source_summary["no_data_organs"],
            "market_level_only_organs": source_summary["market_level_only_organs"],
            "candidate_scoped_source_organs": source_summary["candidate_scoped_source_organs"],
            "directional_source_organs": source_summary["directional_source_organs"],
            "edge_thesis_id": canonical_edge.get("edge_thesis_id") or inquiry_thesis.get("edge_thesis_id"),
            "edge_state": canonical_edge.get("edge_state") or inquiry_thesis.get("edge_state"),
            "edge_score": canonical_edge.get("edge_score") if canonical_edge.get("edge_score") is not None else inquiry_thesis.get("edge_score"),
            "source_backed": canonical_edge.get("source_backed") is True,
            "risk_usable": canonical_edge.get("risk_usable") is True,
            "inquiry_edge_thesis": inquiry_thesis,
            "risk_result": risk_result,
            "lifecycle_result": lifecycle_result,
            "paper_actionability_result": actionability_state,
            "final_blocker": final_blocker,
            "required_to_pass": _required_to_pass(actionability, canonical_edge, responses),
            "created_at": datetime.now(UTC).isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "registry_coverage": validate_decision_critical_coverage(),
        }


def _inquiry_state(responses: list[dict[str, Any]], edge: dict[str, Any], actionability_state: str) -> str:
    if any(response["response_state"] == "ERROR" for response in responses):
        return "ERROR"
    if actionability_state.startswith("BLOCKED") or edge.get("risk_usable") is not True:
        return "BLOCKED"
    if any(response["response_state"] in {"UNAVAILABLE", "MISSING", "STALE"} for response in responses):
        return "PARTIAL"
    return "COMPLETE"


def _final_blocker(actionability: dict[str, Any] | None, edge: dict[str, Any], responses: list[dict[str, Any]]) -> str | None:
    blockers = list((actionability or {}).get("blockers") or [])
    if blockers:
        return str(blockers[0])
    if edge.get("risk_usable") is not True:
        return str(edge.get("blocker_code") or edge.get("edge_state") or "EDGE_NOT_RISK_USABLE")
    for response in responses:
        if response.get("blocker_code"):
            return str(response["blocker_code"])
    return None


def _required_to_pass(actionability: dict[str, Any] | None, edge: dict[str, Any], responses: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    out.extend(str(item) for item in ((actionability or {}).get("required_to_pass") or []))
    out.extend(str(item) for item in (edge.get("required_to_pass") or []))
    for response in responses:
        out.extend(str(item) for item in (response.get("required_to_pass") or []))
    seen: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.append(item)
    return seen


def _session_id(identity: dict[str, Any], bundle: dict[str, Any]) -> str:
    key = "|".join(
        str(value or "")
        for value in (
            identity.get("candidate_id"),
            identity.get("market_id"),
            identity.get("side"),
            identity.get("token_id"),
            identity.get("correlation_id"),
            bundle.get("bundle_id"),
        )
    )
    return f"full_mesh_inquiry_{uuid5(NAMESPACE_URL, key).hex[:32]}"
