from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.paper_actionability import PaperActionabilityService
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.db.connection import DatabaseConnectionFactory
from app.services.trade_opportunity_score import (
    FULL_PAPER_BAND,
    HARD_BLOCKED_BAND,
    NO_TRADE_BAND,
    PAPER_OBSERVATION_BAND,
    SCORE_FORMULA,
    WATCH_ONLY_BAND,
    score_actionability_item,
    summarize_opportunity_scores,
)


class TradeOpportunityScoreControlService:
    """Read-only candidate opportunity score surface.

    This service derives candidate-scoped scores from the same selected row used
    by Paper Actionability. It never writes paper artifacts and never grants
    execution authority.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_scores(self, *, limit: int = 100, offset: int = 0, candidate_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        actionability = PaperActionabilityService(connection_factory=self._factory).list_actionability(
            limit=limit,
            offset=offset,
            candidate_id=candidate_id,
        )
        payload = actionability.get("data") or actionability
        items = []
        for item in payload.get("items") or []:
            score = item.get("opportunity_score") if isinstance(item.get("opportunity_score"), dict) else score_actionability_item(item)
            items.append({**score, "actionability_state": item.get("candidate_paper_actionability_state")})
        items.sort(key=lambda row: float(row.get("overall_score") or 0.0), reverse=True)
        counts = summarize_opportunity_scores([{"opportunity_score": item} for item in items])
        data = {
            "status": "REAL" if items else "MISSING",
            "source": {
                "paper_actionability": "selected candidate-scoped actionability rows",
                "score_formula": "deterministic DATA_ONLY scoring service",
            },
            "last_updated": payload.get("last_updated") or now.isoformat(),
            "freshness_state": payload.get("freshness_state") or "MISSING",
            "readiness_state": "READY" if counts["full_paper_certification"] else "PARTIAL" if items else "UNKNOWN",
            "truth_state": payload.get("truth_state") or "UNKNOWN",
            "score_formula": SCORE_FORMULA,
            "counts": {
                "items": len(items),
                **counts,
            },
            "top_candidates": items[:limit],
            "top_full_certification_candidates": [item for item in items if item.get("decision_band") == FULL_PAPER_BAND],
            "top_paper_observation_candidates": [item for item in items if item.get("decision_band") == PAPER_OBSERVATION_BAND],
            "top_watch_candidates": [item for item in items if item.get("decision_band") == WATCH_ONLY_BAND],
            "hard_blocked_candidates": [item for item in items if item.get("decision_band") == HARD_BLOCKED_BAND],
            "no_trade_candidates": [item for item in items if item.get("decision_band") == NO_TRADE_BAND],
            "warnings": [] if items else ["No candidate opportunity scores are available yet."],
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return _envelope(data)


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status = ControlCenterStatus(payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL")
    envelope = truth_envelope(
        status=status,
        source="trade opportunity score",
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
