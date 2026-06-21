from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.control_center.candidate_event_correlation import build_event_correlation
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.db.connection import DatabaseConnectionFactory
from app.events.types import EventType


EVENT_TYPE = EventType.ORDERBOOK_SNAPSHOT_CREATED.value
STALE_AFTER_SECONDS = 300
REQUIRED_BRAINS = ("liquidity", "risk", "exit", "capital", "lifecycle")
REQUIRED_DELIVERIES = 6


class EventMeshProofService:
    """Read-only Control Center truth for the minimal event-driven mesh proof."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_proofs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = EVENT_TYPE,
        market_id: str | None = None,
        candidate_id: str | None = None,
        correlation_id: str | None = None,
        state: str | None = None,
        include_reactions: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            return self._enveloped(
                self._empty_payload(now, warnings=["Event mesh proof source is unavailable because the database is not configured."]),
                status=ControlCenterStatus.MISSING,
            )
        try:
            with self._factory.connect() as conn:
                missing = [table for table in ("event_log", "brain_outputs", "coordinator_decisions") if not _table_exists(conn, table)]
                if missing:
                    payload = self._empty_payload(now, warnings=[f"Missing mesh proof source tables: {', '.join(missing)}."])
                    payload["mesh_proof_state"] = "MISSING"
                    return self._enveloped(payload, status=ControlCenterStatus.MISSING)
                events = self._fetch_events(
                    conn,
                    limit=max(limit + offset, limit),
                    event_type=event_type or EVENT_TYPE,
                    market_id=market_id,
                    candidate_id=candidate_id,
                    correlation_id=correlation_id,
                )
                items = [self._build_trace(conn, dict(event), include_reactions=include_reactions) for event in events]
                if state:
                    wanted = state.upper()
                    items = [item for item in items if item.get("mesh_proof_state") == wanted or item.get("event_delivery_state") == wanted]
                paged = items[offset : offset + limit]
                counts = self._counts(items)
                latest = _latest_of([item.get("created_at") for item in items])
        except Exception as exc:
            return self._enveloped(
                self._empty_payload(now, errors=[f"Event mesh proof query failed: {type(exc).__name__}: {exc}"]),
                status=ControlCenterStatus.ERROR,
            )

        mesh_state = self._mesh_state(counts)
        freshness_state, truth_state, age = _freshness(latest, now)
        payload = {
            "status": self._status(mesh_state, freshness_state),
            "source": _source_map(),
            "last_updated": latest or now.isoformat(),
            "freshness_state": freshness_state,
            "readiness_state": "READY" if mesh_state == "PROVEN" else "PARTIAL" if mesh_state == "PARTIAL" else "BLOCKED" if mesh_state in {"BLOCKED", "MISSING"} else "UNKNOWN",
            "truth_state": truth_state,
            "mesh_proof_state": mesh_state,
            "counts": counts,
            "top_blockers": self._top_blockers(items),
            "items": paged,
            "warnings": self._warnings(mesh_state, counts),
            "errors": [],
            "limit": limit,
            "offset": offset,
            "event_type": event_type or EVENT_TYPE,
            "include_reactions": include_reactions,
            "generated_at": now.isoformat(),
            "age_seconds": age,
        }
        return self._enveloped(payload, status=ControlCenterStatus(payload["status"]))

    def get_trace(self, correlation_id: str) -> dict[str, Any] | None:
        payload = self.list_proofs(limit=50, correlation_id=correlation_id, include_reactions=True)
        items = payload.get("items") or payload.get("data", {}).get("items") or []
        if not items:
            return None
        data = dict(payload.get("data") or {})
        data["items"] = items
        data["trace"] = items[0]
        return self._enveloped(data, status=ControlCenterStatus(payload["status"]))

    def _fetch_events(
        self,
        conn: Any,
        *,
        limit: int,
        event_type: str,
        market_id: str | None,
        candidate_id: str | None,
        correlation_id: str | None,
    ) -> list[dict[str, Any]]:
        clauses = ["event_type = %s"]
        params: list[Any] = [event_type]
        if market_id:
            clauses.append("(payload_json->>'market_id' = %s OR aggregate_id = %s)")
            params.extend([market_id, market_id])
        if candidate_id:
            clauses.append("payload_json->>'candidate_id' = %s")
            params.append(candidate_id)
        if correlation_id:
            clauses.append("correlation_id = %s")
            params.append(correlation_id)
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM event_log
            WHERE {' AND '.join(clauses)}
            ORDER BY stored_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    def _build_trace(self, conn: Any, event: dict[str, Any], *, include_reactions: bool) -> dict[str, Any]:
        correlation_id = str(event.get("correlation_id") or "")
        brain_rows = conn.execute(
            """
            SELECT *
            FROM brain_outputs
            WHERE correlation_id = %s
              AND generated_by = 'minimal_event_mesh_proof'
            ORDER BY created_at ASC, id ASC
            """,
            (correlation_id,),
        ).fetchall()
        coordinator = conn.execute(
            """
            SELECT *
            FROM coordinator_decisions
            WHERE correlation_id = %s
              AND metadata_json->>'event_type' = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (correlation_id, EVENT_TYPE),
        ).fetchone()
        deliveries = conn.execute(
            """
            SELECT consumer_name, status, error_message, metadata_json, finished_at
            FROM event_delivery_attempts
            WHERE event_id = %s
            ORDER BY id ASC
            """,
            (event["event_id"],),
        ).fetchall() if _table_exists(conn, "event_delivery_attempts") else []

        reactions = [_reaction_from_row(dict(row)) for row in brain_rows]
        brain_names = {reaction["brain"] for reaction in reactions}
        delivery_state = _delivery_state(deliveries)
        coordinator_trace = _coordinator_from_row(dict(coordinator)) if coordinator else _missing_coordinator()
        missing_brains = [brain for brain in REQUIRED_BRAINS if brain not in brain_names]
        blockers: list[str] = []
        if delivery_state == "NO_CONSUMERS":
            blockers.append("NO_CONSUMERS")
        if missing_brains:
            blockers.extend([f"MISSING_{brain.upper()}_REACTION" for brain in missing_brains])
        if not coordinator:
            blockers.append("NO_COORDINATOR_TRACE")
        failed = any(str(row.get("status") or "").upper() in {"FAILED", "DLQ", "RETRY_SCHEDULED"} for row in deliveries)
        if failed:
            blockers.append("CONSUMER_FAILED")
        proof_state = "PROVEN" if not blockers and len(brain_names.intersection(REQUIRED_BRAINS)) == len(REQUIRED_BRAINS) and coordinator else "PARTIAL" if reactions or coordinator else "MISSING"
        if failed:
            proof_state = "BLOCKED"
        payload = event.get("payload_json") or {}
        correlation = build_event_correlation(conn, event, include_bundle=False, include_candidates=False)
        return {
            "event_id": event["event_id"],
            "correlation_id": correlation_id,
            "event_type": event["event_type"],
            "market_id": payload.get("market_id"),
            "candidate_id": payload.get("candidate_id"),
            "side": payload.get("side"),
            "token_id": payload.get("token_id"),
            "orderbook_snapshot_id": payload.get("orderbook_snapshot_id"),
            "event_delivery_state": delivery_state,
            "mesh_proof_state": proof_state,
            "brain_reactions": reactions if include_reactions else [],
            "coordinator": coordinator_trace,
            "candidate_event_link_state": correlation.get("candidate_event_link_state"),
            "candidate_event_actionability_scope": correlation.get("candidate_event_actionability_scope"),
            "correlation_confidence": correlation.get("correlation_confidence"),
            "candidate_link_blockers": correlation.get("blockers") or [],
            "blockers": blockers,
            "warnings": [] if proof_state == "PROVEN" else ["Mesh proof is not fully proven for this event."],
            "created_at": _iso(event.get("stored_at") or event.get("occurred_at")),
            "operator_summary": _summary(proof_state, payload, reactions, coordinator_trace, blockers),
        }

    def _counts(self, items: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "events_seen": len(items),
            "events_with_liquidity_reaction": sum(1 for item in items if _has_brain(item, "liquidity")),
            "events_with_risk_reaction": sum(1 for item in items if _has_brain(item, "risk")),
            "events_with_exit_reaction": sum(1 for item in items if _has_brain(item, "exit")),
            "events_with_capital_reaction": sum(1 for item in items if _has_brain(item, "capital")),
            "events_with_lifecycle_reaction": sum(1 for item in items if _has_brain(item, "lifecycle")),
            "events_with_all_five_reactions": sum(1 for item in items if all(_has_brain(item, brain) for brain in REQUIRED_BRAINS)),
            "events_with_event_native_capital": sum(1 for item in items if _has_event_native_brain(item, "capital")),
            "events_with_event_native_lifecycle": sum(1 for item in items if _has_event_native_brain(item, "lifecycle")),
            "events_linked_to_candidate": sum(1 for item in items if item.get("candidate_event_link_state") == "LINKED_TO_CANDIDATE"),
            "events_market_level_only": sum(1 for item in items if item.get("candidate_event_link_state") == "MARKET_LEVEL_ONLY_WITH_REASON"),
            "events_unlinked": sum(1 for item in items if item.get("candidate_event_link_state") in {"UNLINKED_WITH_REASON", "MISSING_CANDIDATE", "MISSING_EVENT"}),
            "events_ambiguous": sum(1 for item in items if item.get("candidate_event_link_state") == "AMBIGUOUS_MULTIPLE_CANDIDATES"),
            "events_with_coordinator_trace": sum(1 for item in items if item.get("coordinator", {}).get("state") in {"DECISION_CREATED", "PARTIAL_DECISION"}),
            "fully_proven_events": sum(1 for item in items if item.get("mesh_proof_state") == "PROVEN"),
            "partial_events": sum(1 for item in items if item.get("mesh_proof_state") == "PARTIAL"),
            "failed_events": sum(1 for item in items if item.get("mesh_proof_state") == "BLOCKED"),
        }

    def _mesh_state(self, counts: dict[str, int]) -> str:
        if counts["fully_proven_events"] > 0:
            return "PROVEN"
        if counts["events_seen"] == 0:
            return "MISSING"
        if counts["failed_events"] > 0:
            return "BLOCKED"
        if counts["partial_events"] > 0:
            return "PARTIAL"
        return "UNKNOWN"

    def _status(self, mesh_state: str, freshness_state: str) -> str:
        if mesh_state == "PROVEN" and freshness_state == "FRESH":
            return "REAL"
        if mesh_state == "MISSING":
            return "MISSING"
        if mesh_state == "BLOCKED":
            return "LOCKED"
        if freshness_state == "STALE":
            return "STALE"
        return "PARTIAL"

    def _top_blockers(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for item in items:
            counts.update(item.get("blockers") or [])
        return [{"blocker": key, "count": value} for key, value in counts.most_common(10)]

    def _warnings(self, mesh_state: str, counts: dict[str, int]) -> list[str]:
        warnings: list[str] = []
        if mesh_state == "MISSING":
            warnings.append("No orderbook.snapshot.created mesh proof events exist yet.")
        if counts["events_seen"] and counts["fully_proven_events"] == 0:
            warnings.append("Orderbook events exist, but none have full liquidity/risk/exit/capital/lifecycle/coordinator proof.")
        return warnings

    def _empty_payload(self, now: datetime, *, warnings: list[str] | None = None, errors: list[str] | None = None) -> dict[str, Any]:
        return {
            "status": "MISSING" if not errors else "ERROR",
            "source": _source_map(),
            "last_updated": now.isoformat(),
            "freshness_state": "MISSING",
            "readiness_state": "UNKNOWN",
            "truth_state": "UNKNOWN",
            "mesh_proof_state": "MISSING",
            "counts": {
                "events_seen": 0,
                "events_with_liquidity_reaction": 0,
                "events_with_risk_reaction": 0,
                "events_with_exit_reaction": 0,
                "events_with_capital_reaction": 0,
                "events_with_lifecycle_reaction": 0,
                "events_with_all_five_reactions": 0,
                "events_with_event_native_capital": 0,
                "events_with_event_native_lifecycle": 0,
                "events_linked_to_candidate": 0,
                "events_market_level_only": 0,
                "events_unlinked": 0,
                "events_ambiguous": 0,
                "events_with_coordinator_trace": 0,
                "fully_proven_events": 0,
                "partial_events": 0,
                "failed_events": 0,
            },
            "top_blockers": [],
            "items": [],
            "warnings": warnings or [],
            "errors": errors or [],
        }

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        freshness = ControlCenterFreshnessState(payload.get("freshness_state") if payload.get("freshness_state") in {"FRESH", "STALE", "MISSING"} else "MISSING")
        readiness = ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {"READY", "NOT_READY", "PARTIAL", "BLOCKED", "UNKNOWN"} else "UNKNOWN")
        envelope = truth_envelope(
            status=status,
            source="event_log + event_delivery_attempts + brain_outputs + coordinator_decisions",
            truth_state=payload.get("truth_state") if payload.get("truth_state") in {"ACTIVE_FRESH", "LAST_KNOWN", "HISTORICAL_ONLY", "REFRESH_REQUIRED", "UNKNOWN"} else ControlCenterTruthState.UNKNOWN,
            data=payload,
            last_updated=payload.get("last_updated"),
            stale_after_seconds=STALE_AFTER_SECONDS,
            age_seconds=payload.get("age_seconds"),
            freshness_state=freshness,
            runtime_state=ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.STALE if status in {ControlCenterStatus.PARTIAL, ControlCenterStatus.STALE} else ControlCenterRuntimeState.UNKNOWN,
            readiness_state=readiness,
            warnings=payload.get("warnings") or [],
            errors=payload.get("errors") or [],
        ).to_dict()
        return {**payload, **envelope, "data": payload}


def _reaction_from_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata_json") or {}
    return {
        "brain": row.get("brain"),
        "state": metadata.get("reaction_state") or "UNKNOWN",
        "summary": row.get("reasoning_summary"),
        "blockers": metadata.get("blockers") or row.get("risk_flags_json") or [],
        "warnings": metadata.get("warnings") or [],
        "event_native_state": metadata.get("event_native_state") or "UNKNOWN",
        "capital_opinion_state": metadata.get("capital_opinion_state"),
        "lifecycle_opinion_state": metadata.get("lifecycle_opinion_state"),
        "brain_output_id": row.get("brain_output_id"),
        "recommendation": row.get("recommendation"),
        "confidence": _float(row.get("confidence")),
        "created_at": _iso(row.get("created_at")),
    }


def _coordinator_from_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata_json") or {}
    return {
        "state": metadata.get("coordinator_state") or "DECISION_CREATED",
        "decision": metadata.get("decision") or row.get("final_state"),
        "reason": row.get("primary_reason"),
        "conflicts": metadata.get("conflicts") or [],
        "mesh_consensus_state": metadata.get("mesh_consensus_state"),
        "capital_opinion_state": metadata.get("capital_opinion_state"),
        "lifecycle_opinion_state": metadata.get("lifecycle_opinion_state"),
        "required_to_progress": row.get("required_reviews_json") or [],
        "coordinator_decision_id": row.get("coordinator_decision_id"),
        "created_at": _iso(row.get("created_at")),
    }


def _missing_coordinator() -> dict[str, Any]:
    return {
        "state": "NO_DECISION",
        "decision": "NO_ACTION",
        "reason": "No coordinator trace exists for this event correlation.",
        "conflicts": [],
        "required_to_progress": ["Coordinator consumer must produce a trace."],
    }


def _delivery_state(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "NO_CONSUMERS"
    statuses = {str(row.get("status") or "").upper() for row in rows}
    if statuses <= {"SUCCESS"} and len(rows) >= REQUIRED_DELIVERIES:
        return "DELIVERED"
    if statuses.intersection({"FAILED", "DLQ", "RETRY_SCHEDULED"}):
        return "CONSUMER_FAILED"
    if "SUCCESS" in statuses:
        return "PARTIAL_DELIVERY"
    return "UNKNOWN"


def _has_brain(item: dict[str, Any], brain: str) -> bool:
    return any(reaction.get("brain") == brain for reaction in item.get("brain_reactions") or [])


def _has_event_native_brain(item: dict[str, Any], brain: str) -> bool:
    return any(
        reaction.get("brain") == brain and reaction.get("event_native_state") == "EVENT_NATIVE"
        for reaction in item.get("brain_reactions") or []
    )


def _freshness(latest: str | None, now: datetime) -> tuple[str, str, float | None]:
    if not latest:
        return "MISSING", "UNKNOWN", None
    try:
        dt = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        age = max(0.0, (now - dt).total_seconds())
    except ValueError:
        return "STALE", "LAST_KNOWN", None
    if age <= STALE_AFTER_SECONDS:
        return "FRESH", "ACTIVE_FRESH", age
    return "STALE", "LAST_KNOWN", age


def _summary(
    proof_state: str,
    payload: dict[str, Any],
    reactions: list[dict[str, Any]],
    coordinator: dict[str, Any],
    blockers: list[str],
) -> str:
    if proof_state == "PROVEN":
        return f"Orderbook event for market {payload.get('market_id')} woke liquidity, risk, exit, capital, lifecycle, and coordinator."
    if blockers:
        return f"Orderbook event for market {payload.get('market_id')} is not fully proven: {', '.join(blockers)}."
    return f"Orderbook event for market {payload.get('market_id')} has {len(reactions)} reactions and coordinator state {coordinator.get('state')}."


def _source_map() -> dict[str, str]:
    return {
        "events": "event_log",
        "delivery": "event_delivery_attempts",
        "consumers": "event_consumers",
        "brain_reactions": "brain_outputs",
        "coordinator": "coordinator_decisions",
        "source_orderbook": "orderbook_snapshots",
    }


def _latest_of(values: list[Any]) -> str | None:
    cleaned = [str(value) for value in values if value]
    return max(cleaned) if cleaned else None


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None
