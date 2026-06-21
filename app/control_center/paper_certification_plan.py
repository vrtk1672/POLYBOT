from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.trade_opportunity_score import TradeOpportunityScoreControlService
from app.control_center.unified_blockers import unified_blocker
from app.services.paper_observation_policy import PaperObservationPolicyReviewService


class PaperCertificationPlanService:
    """Dry Phase 10 certification plan. This service never activates paper."""

    def get_plan(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        score_payload = TradeOpportunityScoreControlService().list_scores(limit=100)
        score_counts = (score_payload.get("data") or score_payload).get("counts") or {}
        policy_payload = PaperObservationPolicyReviewService().summary(limit=5)
        policy_counts = policy_payload.get("counts") or {}
        payload = {
            "status": "REAL",
            "source": {"plan": "static pre-paper certification contract"},
            "last_updated": now.isoformat(),
            "freshness_state": "FRESH",
            "readiness_state": "PARTIAL",
            "truth_state": "ACTIVE_FRESH",
            "plan_state": "DEFINED_NOT_STARTED",
            "duration": {"recommended_minutes": 15, "minimum_cycles": 4, "maximum_cycles": 10},
            "allowed_actions": ["POST system-on", "POST paper-on only in Phase 10 after pre-check acceptance", "POST system-off cleanup"],
            "forbidden_actions": ["POST start-full-monitor-run", "POST shadow", "POST live", "POST manual trade", "POST execution action"],
            "pre_checks": [
                "pre-paper-safety endpoint reviewed",
                "candidate-scoped event exists",
                "paper-actionability endpoint reviewed",
                "paper readiness blockers are understood",
                "before counts captured",
            ],
            "start_conditions": [
                "SYSTEM ON smoke passes",
                "Paper Simulation ON is explicitly authorized by Phase 10 prompt",
                "Live and Shadow remain disabled",
                "candidate-scoped mesh evidence exists or accepted YELLOW risk is documented",
            ],
            "stop_conditions": [
                "forbidden artifact count increases",
                "State Governor denies mode",
                "paper order/fill/position appears outside allowed Paper Simulation window",
                "SYSTEM OFF cleanup fails",
            ],
            "before_after_counts": [
                "event_log",
                "orderbook_snapshots",
                "brain_outputs",
                "coordinator_decisions",
                "paper_intents",
                "paper_orders",
                "paper_fills",
                "paper_positions",
                "live_orders",
                "positions",
            ],
            "expected_artifacts": ["paper_intents only if all gates pass", "no_trade/blocker records for non-actionable candidates"],
            "allowed_artifact_types": ["paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes"],
            "forbidden_artifact_types": ["live_orders", "shadow_orders", "orders_v2 live orders", "fills_v2 live fills", "positions live positions"],
            "green_criteria": [
                "SYSTEM ON works",
                "Paper Simulation ON explicitly enabled only in Phase 10",
                "candidate-scoped price ready",
                "all-five mesh bundle exists",
                "paper actionability exists",
                "paper artifacts only appear inside Paper Simulation and only if gates pass",
                "no live/shadow artifacts",
                "SYSTEM OFF cleanup works",
            ],
            "yellow_criteria": [
                "Paper path remains blocked but every blocker uses unified shape",
                "candidate-scoped evidence remains partial with accepted documented risk",
            ],
            "red_criteria": [
                "Paper Simulation activates before Phase 10 authorization",
                "live/shadow artifact appears",
                "market-level event treated as candidate actionable",
                "State Governor bypassed",
                "SYSTEM OFF cleanup fails",
            ],
            "cleanup_procedure": ["POST system-off", "verify Paper Simulation OFF", "capture after counts", "verify forbidden counts unchanged"],
            "rollback_abort_rules": ["If forbidden artifact count increases, stop and report RED.", "Do not delete DB or reset volumes."],
            "blockers": ["PAPER_SIMULATION_OFF"],
            "opportunity_score_counts": {
                "full_certification_count": int(score_counts.get("full_paper_certification") or 0),
                "paper_observation_eligible_count": int(score_counts.get("paper_observation_eligible") or 0),
                "watch_only_count": int(score_counts.get("watch_only") or 0),
                "hard_blocked_count": int(score_counts.get("hard_blocked") or 0),
            },
            "paper_observation_policy": {
                "classification_only": True,
                "execution_enabled": False,
                "operator_policy_required": True,
                "shadow_ready": False,
                "live_ready": False,
                "reviewed_count": int(policy_counts.get("total_paper_observation_classifications_reviewed") or 0),
                "eligible_count": int(policy_counts.get("observation_policy_eligible_count") or 0),
                "watch_count": int(policy_counts.get("observation_policy_watch_count") or 0),
                "blocked_count": int(policy_counts.get("observation_policy_blocked_count") or 0),
                "incomplete_count": int(policy_counts.get("observation_policy_incomplete_count") or 0),
                "observation_execution_mode_implemented": False,
                "paper_intent_creation_allowed": False,
            },
            "unified_blockers": [unified_blocker("PAPER_SIMULATION_OFF", source="paper_certification_plan")],
            "warnings": ["This plan is dry-only and does not activate Paper Simulation."],
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return _envelope(payload)


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    envelope = truth_envelope(
        status=ControlCenterStatus.REAL,
        source="paper certification dry plan",
        truth_state=ControlCenterTruthState.ACTIVE_FRESH,
        data=payload,
        last_updated=payload.get("last_updated"),
        stale_after_seconds=86400,
        freshness_state=ControlCenterFreshnessState.FRESH,
        runtime_state=ControlCenterRuntimeState.RUNNING,
        readiness_state=ControlCenterReadinessState.PARTIAL,
        warnings=payload.get("warnings") or [],
        errors=payload.get("errors") or [],
    ).to_dict()
    return {**envelope, **payload, "data": payload}
