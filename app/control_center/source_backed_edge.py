from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory


class SourceBackedEdgeControlService:
    """Read-only view over Risk's canonical source-backed Edge Thesis metadata."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_edges(self, *, limit: int = 50, offset: int = 0, candidate_id: str | None = None, market_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return _payload("MISSING", now, [], warnings=["Database is not configured."])
        with self._factory.connect() as conn:
            if not _table_exists(conn, "risk_evidence_mesh_evaluations"):
                return _payload("MISSING", now, [], warnings=["risk_evidence_mesh_evaluations table is missing."])
            clauses = ["metadata_json ? 'edge_thesis'"]
            params: list[Any] = []
            if candidate_id:
                clauses.append("subject_id=%s")
                params.append(candidate_id)
            if market_id:
                clauses.append("market_id=%s")
                params.append(market_id)
            params.extend([limit, offset])
            rows = conn.execute(
                f"""
                SELECT *
                FROM risk_evidence_mesh_evaluations
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            ).fetchall()
        items = [_item(dict(row)) for row in rows]
        return _payload("REAL" if items else "MISSING", now, items)


def _payload(status: str, now: datetime, items: list[dict[str, Any]], *, warnings: list[str] | None = None) -> dict[str, Any]:
    states = Counter(str(item.get("edge_state") or "EDGE_UNKNOWN") for item in items)
    return {
        "status": status,
        "source": {
            "edge_thesis": "risk_evidence_mesh_evaluations.metadata_json.edge_thesis",
            "risk_evidence": "risk_evidence_mesh_evaluations",
        },
        "last_updated": items[0].get("updated_at") or items[0]["created_at"] if items else now.isoformat(),
        "freshness_state": "FRESH" if items else "MISSING",
        "readiness_state": "READY" if any(item.get("edge_state") == "EDGE_SUPPORTED" and item.get("risk_usable") for item in items) else "PARTIAL" if items else "UNKNOWN",
        "truth_state": "ACTIVE_FRESH" if items else "UNKNOWN",
        "counts": {
            "items": len(items),
            "edge_supported": states.get("EDGE_SUPPORTED", 0),
            "edge_watch": states.get("EDGE_WATCH", 0),
            "edge_weak": states.get("EDGE_WEAK", 0),
            "no_source_backed_edge": states.get("NO_SOURCE_BACKED_EDGE", 0),
            "source_conflict": states.get("SOURCE_CONFLICT", 0),
            "edge_stale": states.get("EDGE_STALE", 0),
            "no_current_directional_edge": states.get("NO_CURRENT_DIRECTIONAL_EDGE", 0),
            "derived_signals_watch_only": states.get("DERIVED_SIGNALS_WATCH_ONLY", 0),
            "edge_source_organs_unavailable": states.get("EDGE_SOURCE_ORGANS_UNAVAILABLE", 0),
            "risk_usable": sum(1 for item in items if item.get("risk_usable") is True),
            "source_backed": sum(1 for item in items if item.get("source_backed") is True),
            "source_organs_queried": sum(int(item.get("source_organs_queried") or 0) for item in items),
            "source_organs_unavailable": sum(len(item.get("source_organs_unavailable") or []) for item in items),
            "directional_sources_found": sum(int(item.get("directional_sources_found") or 0) for item in items),
        },
        "why_edge_supported_zero": _why_zero(items),
        "items": items,
        "warnings": warnings or ([] if items else ["No source-backed edge theses exist yet."]),
        "errors": [],
    }


def _item(row: dict[str, Any]) -> dict[str, Any]:
    thesis = ((row.get("metadata_json") or {}).get("edge_thesis") or {}) if isinstance(row.get("metadata_json"), dict) else {}
    return {
        "edge_thesis_id": thesis.get("edge_thesis_id"),
        "candidate_id": thesis.get("candidate_id") or row.get("subject_id"),
        "market_id": thesis.get("market_id") or row.get("market_id"),
        "condition_id": thesis.get("condition_id") or row.get("condition_id"),
        "side": thesis.get("side") or row.get("side"),
        "token_id": thesis.get("token_id") or row.get("token_id"),
        "correlation_id": thesis.get("correlation_id"),
        "event_id": thesis.get("event_id"),
        "edge_state": thesis.get("edge_state") or row.get("edge_status"),
        "edge_score": thesis.get("edge_score") or row.get("evidence_quality_score"),
        "risk_evidence_id": row.get("evaluation_id"),
        "source_refresh_cycle_id": thesis.get("source_refresh_cycle_id") or ((row.get("metadata_json") or {}).get("source_refresh_cycle_id") if isinstance(row.get("metadata_json"), dict) else None),
        "propagation_context": thesis.get("propagation_context") or {},
        "fresh_sources_used": thesis.get("fresh_sources_used") or [],
        "stale_sources_ignored": thesis.get("stale_sources_ignored") or [],
        "stale_sources_blocking": thesis.get("stale_sources_blocking") or [],
        "derived_signals_used": thesis.get("derived_signal_ids") or thesis.get("derived_signals_used") or [],
        "why_edge_state": thesis.get("ai_thesis") or thesis.get("blocker_code"),
        "source_backed": thesis.get("source_backed") is True,
        "risk_usable": thesis.get("risk_usable") is True,
        "primary_edge_type": thesis.get("primary_edge_type") or row.get("edge_source_type"),
        "supporting_neurons": thesis.get("supporting_neurons") or [],
        "opposing_neurons": thesis.get("opposing_neurons") or [],
        "supporting_sources": thesis.get("supporting_sources") or [],
        "opposing_sources": thesis.get("opposing_sources") or [],
        "ai_thesis": thesis.get("ai_thesis"),
        "ai_counter_thesis": thesis.get("ai_counter_thesis"),
        "ai_review_model": thesis.get("ai_review_model"),
        "ai_review_status": thesis.get("ai_review_status"),
        "blocker_code": thesis.get("blocker_code"),
        "required_to_pass": thesis.get("required_to_pass") or [],
        "risk_decision": row.get("risk_decision"),
        "risk_blocker_subtype": row.get("risk_blocker_subtype"),
        "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else row.get("created_at"),
        "updated_at": row.get("updated_at").isoformat() if hasattr(row.get("updated_at"), "isoformat") else row.get("updated_at"),
        "source_records": thesis.get("source_records") or [],
        "source_organ_status": thesis.get("source_organ_status") or {},
        "source_organs_queried": thesis.get("source_organs_queried") or 0,
        "source_organs_unavailable": thesis.get("source_organs_unavailable") or [],
        "source_organs_no_data": thesis.get("source_organs_no_data") or [],
        "missing_source_organs": thesis.get("missing_source_organs") or [],
        "directional_sources_found": thesis.get("directional_sources_found") or 0,
        "operator_summary": _summary(thesis, row),
    }


def _summary(thesis: dict[str, Any], row: dict[str, Any]) -> str:
    state = thesis.get("edge_state") or row.get("edge_status")
    if state == "EDGE_SUPPORTED" and thesis.get("risk_usable") is True:
        return "Candidate has a source-backed, risk-usable Edge Thesis."
    return f"Candidate edge thesis is {state}; Risk decision is {row.get('risk_decision')} via {row.get('risk_blocker_subtype')}."


def _why_zero(items: list[dict[str, Any]]) -> list[str]:
    if any(item.get("edge_state") == "EDGE_SUPPORTED" for item in items):
        return []
    reasons: list[str] = []
    if any(item.get("edge_state") == "EDGE_SOURCE_ORGANS_UNAVAILABLE" for item in items):
        reasons.append("Source organs were queried but unavailable or missing configuration.")
    if any(item.get("edge_state") == "EDGE_WATCH" for item in items):
        reasons.append("Available evidence reached watch-level only.")
    if any(item.get("edge_state") == "DERIVED_SIGNALS_WATCH_ONLY" for item in items):
        reasons.append("Fresh derived signals reached watch-level only.")
    if any(item.get("edge_state") == "NO_CURRENT_DIRECTIONAL_EDGE" for item in items):
        reasons.append("Fresh source truth reached Edge, but no current directional edge was found.")
    if any(item.get("edge_state") == "EDGE_STALE" for item in items):
        reasons.append("Some source evidence is stale.")
    if any(item.get("edge_state") == "NO_SOURCE_BACKED_EDGE" for item in items):
        reasons.append("No fresh directional source-backed evidence was found.")
    return reasons or ["No edge items were available to evaluate."]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])
