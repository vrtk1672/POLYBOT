from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.control_center.paper_actionability import PaperActionabilityService
from app.control_center.source_backed_edge import SourceBackedEdgeControlService
from app.db.connection import DatabaseConnectionFactory
from app.services.full_mesh_inquiry import FullMeshInquiryOrchestrator
from app.services.full_mesh_registry import full_mesh_registry, validate_decision_critical_coverage


class FullMeshInquiryControlService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_inquiries(self, *, limit: int = 50, offset: int = 0, candidate_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        bundle_payload = MeshEvidenceBundleService(connection_factory=self._factory).list_bundles(
            limit=limit,
            offset=offset,
            candidate_id=candidate_id,
            include_opinions=True,
            include_conflicts=True,
        )
        actionability_payload = PaperActionabilityService(connection_factory=self._factory).list_actionability(
            limit=limit,
            offset=offset,
            candidate_id=candidate_id,
        )
        actionability_by_key = {
            _actionability_key(item): item
            for item in actionability_payload.get("items", [])
            if _actionability_key(item)
        }
        edge_service = SourceBackedEdgeControlService(connection_factory=self._factory)
        orchestrator = FullMeshInquiryOrchestrator(connection_factory=self._factory)
        sessions: list[dict[str, Any]] = []
        for bundle in (bundle_payload.get("items") or bundle_payload.get("data", {}).get("items") or []):
            edge = {}
            if bundle.get("candidate_id"):
                edge_items = edge_service.list_edges(limit=1, candidate_id=str(bundle.get("candidate_id"))).get("items") or []
                edge = dict(edge_items[0]) if edge_items else {}
            actionability = actionability_by_key.get(str(bundle.get("bundle_id"))) or actionability_by_key.get(str(bundle.get("candidate_id") or ""))
            sessions.append(orchestrator.build_session(bundle, edge=edge, actionability=actionability))
        states = Counter(session["inquiry_state"] for session in sessions)
        edge_states = Counter(str(session.get("edge_state") or "UNKNOWN") for session in sessions)
        source_summary = _source_summary(sessions)
        return {
            "status": "REAL" if sessions else "MISSING",
            "source": {
                "mesh_evidence_bundles": "event_log + brain_outputs + coordinator_decisions",
                "edge_thesis": "risk_evidence_mesh_evaluations.metadata_json.edge_thesis",
                "actionability": "paper_actionability read-only contract",
                "registry": "full_mesh_registry + neuron_registry truth",
            },
            "last_updated": sessions[0]["completed_at"] if sessions else now.isoformat(),
            "freshness_state": "FRESH" if sessions else "MISSING",
            "readiness_state": "READY" if any(session.get("risk_usable") for session in sessions) else "PARTIAL" if sessions else "UNKNOWN",
            "truth_state": "ACTIVE_FRESH" if sessions else "UNKNOWN",
            "counts": {
                "sessions": len(sessions),
                "complete": states.get("COMPLETE", 0),
                "partial": states.get("PARTIAL", 0),
                "blocked": states.get("BLOCKED", 0),
                "error": states.get("ERROR", 0),
                "edge_supported": edge_states.get("EDGE_SUPPORTED", 0),
                "edge_watch": edge_states.get("EDGE_WATCH", 0),
                "risk_usable": sum(1 for session in sessions if session.get("risk_usable") is True),
                "source_backed": sum(1 for session in sessions if session.get("source_backed") is True),
                "source_backed_edge_count": sum(1 for session in sessions if session.get("source_backed") is True),
                "edge_source_unavailable_count": edge_states.get("EDGE_SOURCE_ORGANS_UNAVAILABLE", 0),
                "neurons_requested": sum(int(session.get("neurons_requested") or 0) for session in sessions),
                "neurons_responded": sum(int(session.get("neurons_responded") or 0) for session in sessions),
                "neurons_unavailable": sum(int(session.get("neurons_unavailable") or 0) for session in sessions),
                "neurons_error": sum(int(session.get("neurons_error") or 0) for session in sessions),
                **source_summary["counts"],
            },
            "organ_status_summary": source_summary,
            "source_organs_active": source_summary["source_organs_active"],
            "source_organs_passive": source_summary["source_organs_passive"],
            "source_organs_unavailable": source_summary["source_organs_unavailable"],
            "missing_config_organs": source_summary["missing_config_organs"],
            "no_data_organs": source_summary["no_data_organs"],
            "market_level_only_organs": source_summary["market_level_only_organs"],
            "candidate_scoped_source_organs": source_summary["candidate_scoped_source_organs"],
            "directional_source_organs": source_summary["directional_source_organs"],
            "registry": [item.to_api_dict() for item in full_mesh_registry()],
            "registry_coverage": validate_decision_critical_coverage(),
            "items": sessions,
            "top_missing_neurons": _top_values(sessions, "missing_neurons"),
            "top_final_blockers": _top_values(sessions, "final_blocker"),
            "warnings": [] if sessions else ["No full mesh inquiry sessions could be assembled."],
            "errors": [],
            "generated_at": now.isoformat(),
        }


def _actionability_key(item: dict[str, Any]) -> str | None:
    return str(item.get("mesh_bundle_id") or item.get("candidate_id") or "") or None


def _top_values(items: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for item in items:
        value = item.get(key)
        if isinstance(value, list):
            values.extend(str(part) for part in value if part)
        elif value:
            values.append(str(value))
    return [name for name, _ in Counter(values).most_common(10)]


def _source_summary(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    active: list[str] = []
    passive: list[str] = []
    unavailable: list[str] = []
    missing_config: list[str] = []
    no_data: list[str] = []
    market_level: list[str] = []
    candidate_scoped: list[str] = []
    directional: list[str] = []
    by_state: Counter[str] = Counter()
    for session in sessions:
        summary = session.get("source_organ_status_summary") or {}
        active.extend(_names_from_summary(summary, "source_organs_active"))
        passive.extend(_names_from_summary(summary, "source_organs_passive"))
        unavailable.extend(_names_from_summary(summary, "source_organs_unavailable"))
        missing_config.extend(_names_from_summary(summary, "missing_config_organs"))
        no_data.extend(_names_from_summary(summary, "no_data_organs"))
        market_level.extend(_names_from_summary(summary, "market_level_only_organs"))
        candidate_scoped.extend(_names_from_summary(summary, "candidate_scoped_source_organs"))
        directional.extend(_names_from_summary(summary, "directional_source_organs"))
        by_state.update(summary.get("by_state") or {})
    active_names = active + market_level + candidate_scoped
    return {
        "counts": {
            "source_organs_active": len(active_names),
            "source_organs_passive": len(passive),
            "source_organs_unavailable": len(unavailable),
            "missing_config_organs": len(missing_config),
            "no_data_organs": len(no_data),
            "market_level_only_organs": len(market_level),
            "candidate_scoped_source_organs": len(candidate_scoped),
            "directional_source_organs": len(directional),
        },
        "source_organs_active": _top_counter(active_names),
        "source_organs_passive": _top_counter(passive),
        "source_organs_unavailable": _top_counter(unavailable),
        "missing_config_organs": _top_counter(missing_config),
        "no_data_organs": _top_counter(no_data),
        "market_level_only_organs": _top_counter(market_level),
        "candidate_scoped_source_organs": _top_counter(candidate_scoped),
        "directional_source_organs": _top_counter(directional),
        "by_state": dict(by_state),
    }


def _names_from_summary(summary: dict[str, Any], key: str) -> list[str]:
    value = summary.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, int):
        return []
    return []


def _top_counter(values: list[str]) -> list[str]:
    return [name for name, _ in Counter(values).most_common(20)]
