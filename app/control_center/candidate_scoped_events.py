from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.candidate_event_correlation import CandidateEventCorrelationService
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.unified_blockers import unified_blockers
from app.db.connection import DatabaseConnectionFactory


class CandidateScopedEventsService:
    """Read-only view of candidate-scoped orderbook snapshot events."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_events(self, *, limit: int = 50, offset: int = 0, candidate_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        correlation = CandidateEventCorrelationService(connection_factory=self._factory).list_correlations(
            limit=limit,
            offset=offset,
            candidate_id=candidate_id,
            include_bundle=True,
            include_candidates=True,
        )
        data = dict(correlation.get("data") or correlation)
        items = [self._event_item(item) for item in data.get("items") or []]
        counts = {
            "events_checked": data.get("counts", {}).get("events_checked", 0),
            "candidate_event_scoped": sum(1 for item in items if item["candidate_scoped_event_state"] == "CANDIDATE_EVENT_SCOPED"),
            "market_event_only": sum(1 for item in items if item["candidate_scoped_event_state"] == "MARKET_EVENT_ONLY"),
            "unlinked_with_reason": sum(1 for item in items if item["candidate_scoped_event_state"] == "UNLINKED_WITH_REASON"),
            "ambiguous_candidate_event": sum(1 for item in items if item["candidate_scoped_event_state"] == "AMBIGUOUS_CANDIDATE_EVENT"),
            "token_side_mismatch": sum(1 for item in items if item["candidate_scoped_event_state"] == "TOKEN_SIDE_MISMATCH"),
        }
        state = "READY" if counts["candidate_event_scoped"] else "PARTIAL" if counts["events_checked"] else "UNKNOWN"
        payload = {
            "status": "REAL" if counts["events_checked"] else "MISSING",
            "source": {"candidate_event_correlation": "event_log + paper_eligibility_candidates"},
            "last_updated": data.get("last_updated") or now.isoformat(),
            "freshness_state": data.get("freshness_state") or "MISSING",
            "readiness_state": state,
            "truth_state": data.get("truth_state") or "UNKNOWN",
            "counts": counts,
            "items": items,
            "blockers": [] if counts["candidate_event_scoped"] else ["NO_CANDIDATE_SCOPED_EVENT"],
            "unified_blockers": [] if counts["candidate_event_scoped"] else [unified_blockers(["NO_CANDIDATE_SCOPED_EVENT"], source="candidate_scoped_events")[0]],
            "warnings": [] if counts["candidate_event_scoped"] else ["No latest event is candidate-scoped and candidate-actionable."],
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return _envelope(payload)

    def _event_item(self, item: dict[str, Any]) -> dict[str, Any]:
        link_state = item.get("candidate_event_link_state")
        mapped = {
            "LINKED_TO_CANDIDATE": "CANDIDATE_EVENT_SCOPED",
            "MARKET_LEVEL_ONLY_WITH_REASON": "MARKET_EVENT_ONLY",
            "UNLINKED_WITH_REASON": "UNLINKED_WITH_REASON",
            "AMBIGUOUS_MULTIPLE_CANDIDATES": "AMBIGUOUS_CANDIDATE_EVENT",
            "TOKEN_SIDE_MISMATCH": "TOKEN_SIDE_MISMATCH",
        }.get(str(link_state or ""), "UNKNOWN")
        blockers = list(item.get("blockers") or [])
        return {
            "event_id": item.get("event_id"),
            "correlation_id": item.get("correlation_id"),
            "candidate_id": item.get("candidate_id"),
            "market_id": item.get("market_id"),
            "side": item.get("side"),
            "token_id": item.get("token_id"),
            "orderbook_snapshot_id": item.get("orderbook_snapshot_id"),
            "candidate_scoped_event_state": mapped,
            "candidate_event_link_state": link_state,
            "candidate_event_actionability_scope": item.get("candidate_event_actionability_scope"),
            "correlation_confidence": item.get("correlation_confidence"),
            "mesh_bundle_id": item.get("mesh_bundle_id"),
            "coordinator_decision": item.get("coordinator_decision"),
            "execution_allowed": False,
            "blockers": blockers,
            "unified_blockers": unified_blockers(
                blockers,
                source="candidate_scoped_events",
                candidate_id=item.get("candidate_id"),
                event_id=item.get("event_id"),
                correlation_id=item.get("correlation_id"),
                market_id=item.get("market_id"),
                side=item.get("side"),
                token_id=item.get("token_id"),
            ),
            "required_to_pass": item.get("required_to_link_candidate") or [],
            "operator_summary": item.get("operator_summary"),
        }


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status = ControlCenterStatus(payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL")
    envelope = truth_envelope(
        status=status,
        source="candidate-scoped events: candidate_event_correlation",
        truth_state=payload.get("truth_state") if payload.get("truth_state") in {item.value for item in ControlCenterTruthState} else ControlCenterTruthState.UNKNOWN,
        data=payload,
        last_updated=payload.get("last_updated"),
        stale_after_seconds=300,
        freshness_state=ControlCenterFreshnessState(payload.get("freshness_state") if payload.get("freshness_state") in {"FRESH", "STALE", "MISSING"} else "MISSING"),
        runtime_state=ControlCenterRuntimeState.RUNNING if status == ControlCenterStatus.REAL else ControlCenterRuntimeState.UNKNOWN,
        readiness_state=ControlCenterReadinessState(payload.get("readiness_state") if payload.get("readiness_state") in {item.value for item in ControlCenterReadinessState} else "UNKNOWN"),
        warnings=payload.get("warnings") or [],
        errors=payload.get("errors") or [],
    ).to_dict()
    return {**envelope, **payload, "data": payload}
