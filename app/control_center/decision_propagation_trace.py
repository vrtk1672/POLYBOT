from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.paper_actionability import PaperActionabilityService
from app.control_center.source_backed_edge import SourceBackedEdgeControlService
from app.control_center.source_refresh_status import SourceRefreshStatusService
from app.db.connection import DatabaseConnectionFactory


class DecisionPropagationTraceService:
    """Read-only trace from source refresh through Edge/Risk and paper actionability."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_trace(self, *, limit: int = 20, candidate_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        source_refresh = SourceRefreshStatusService(connection_factory=self._factory).get_status()
        edges = SourceBackedEdgeControlService(connection_factory=self._factory).list_edges(limit=limit, candidate_id=candidate_id)
        actionability = PaperActionabilityService(connection_factory=self._factory).list_actionability(limit=limit, candidate_id=candidate_id)
        edge_items = edges.get("items") or []
        action_items = actionability.get("items") or []
        action_by_candidate = {str(item.get("candidate_id")): item for item in action_items if item.get("candidate_id")}
        traces = []
        for edge in edge_items:
            candidate = str(edge.get("candidate_id") or "")
            action = action_by_candidate.get(candidate, {})
            opportunity_score = action.get("opportunity_score") if isinstance(action.get("opportunity_score"), dict) else {}
            risk_capital_trace = action.get("risk_capital_gate_trace") if isinstance(action.get("risk_capital_gate_trace"), dict) else {}
            trade_thesis_trace = risk_capital_trace.get("trade_thesis_trace") if isinstance(risk_capital_trace.get("trade_thesis_trace"), dict) else {}
            traces.append(
                {
                    "candidate_id": edge.get("candidate_id"),
                    "market_id": edge.get("market_id"),
                    "side": edge.get("side"),
                    "token_id": edge.get("token_id"),
                    "source_refresh_cycle_id": edge.get("source_refresh_cycle_id"),
                    "mesh_inquiry_session_id": (edge.get("propagation_context") or {}).get("mesh_inquiry_session_id"),
                    "edge_thesis_id": edge.get("edge_thesis_id"),
                    "risk_evidence_id": edge.get("risk_evidence_id"),
                    "lifecycle_decision_id": action.get("lifecycle_decision_id") or (action.get("lifecycle_gate_trace") or {}).get("lifecycle_decision_id") or (edge.get("propagation_context") or {}).get("lifecycle_decision_id"),
                    "capital_evidence_id": action.get("capital_evidence_id") or (action.get("lifecycle_gate_trace") or {}).get("capital_evidence_id"),
                    "orderbook_snapshot_id": action.get("orderbook_snapshot_id") or (action.get("lifecycle_gate_trace") or {}).get("orderbook_snapshot_id"),
                    "selected_candidate_event_id": action.get("selected_candidate_event_id") or action.get("event_id"),
                    "selected_event_correlation_id": action.get("correlation_id"),
                    "selected_candidate_event_scope": action.get("candidate_event_scope") or action.get("candidate_event_actionability_scope"),
                    "selected_candidate_event_link_state": action.get("candidate_event_link_state"),
                    "selected_orderbook_snapshot_id": action.get("selected_orderbook_snapshot_id") or action.get("candidate_price_orderbook_snapshot_id") or action.get("orderbook_snapshot_id"),
                    "selected_source_refresh_cycle_id": action.get("source_refresh_cycle_id") or edge.get("source_refresh_cycle_id"),
                    "market_memory_id": action.get("market_memory_id"),
                    "market_memory_status": action.get("market_memory_status"),
                    "market_memory_freshness": action.get("market_memory_freshness"),
                    "market_identity_verification_state": action.get("market_identity_verification_state"),
                    "token_verification_state": action.get("token_verification_state"),
                    "source_event_memory_ids": action.get("source_event_memory_ids") or [],
                    "event_to_market_link_ids": action.get("event_to_market_link_ids") or [],
                    "strongest_event_link_type": action.get("strongest_event_link_type"),
                    "strongest_event_link_confidence": action.get("strongest_event_link_confidence") or 0.0,
                    "recent_source_event_link_state": action.get("recent_source_event_link_state") or "EVENT_NOT_LINKED",
                    "recall_link_state": action.get("recall_link_state") or action.get("recent_source_event_link_state") or "EVENT_NOT_LINKED",
                    "event_link_actionability_hint": action.get("event_link_actionability_hint") or "NOT_RELEVANT",
                    "token_side_resolution_state": action.get("token_side_resolution_state") or "TOKEN_SIDE_UNKNOWN",
                    "event_link_guardrail_reason": action.get("event_link_guardrail_reason"),
                    "recent_source_event_count": action.get("recent_source_event_count") or 0,
                    "recent_directional_event_state": action.get("recent_directional_event_state") or "UNKNOWN",
                    "targeted_revalidation_id": action.get("targeted_revalidation_id"),
                    "revalidation_state": action.get("latest_targeted_revalidation_state"),
                    "refreshed_orderbook_snapshot_id": action.get("refreshed_orderbook_snapshot_id"),
                    "orderbook_refresh_state_from_revalidation": action.get("orderbook_refresh_state_from_revalidation"),
                    "movement_state_from_revalidation": action.get("movement_state_from_revalidation"),
                    "already_priced_in_state": action.get("already_priced_in_state_from_revalidation"),
                    "candidate_generation_later_state": action.get("revalidation_candidate_generation_later_state"),
                    "candidate_generation_later_eligible": action.get("candidate_generation_later_eligible"),
                    "proactive_candidate_seed_id": action.get("proactive_seed_id") or action.get("latest_proactive_candidate_seed_id"),
                    "multi_trigger_id": action.get("multi_trigger_id"),
                    "trigger_type": action.get("trigger_type"),
                    "trigger_score": action.get("trigger_score"),
                    "trigger_reasons": action.get("trigger_reasons") or [],
                    "seed_generation_source": action.get("seed_generation_source"),
                    "proactive_source_event_id": (action.get("source_event_memory_ids") or [None])[0] if isinstance(action.get("source_event_memory_ids"), list) else None,
                    "proactive_seed_research_only": action.get("research_only"),
                    "proactive_seed_execution_allowed": action.get("seed_execution_allowed"),
                    "mesh_handoff_state": action.get("mesh_handoff_state"),
                    "seed_mesh_inquiry_id": action.get("seed_mesh_inquiry_id"),
                    "seed_mesh_result_state": action.get("seed_mesh_result_state"),
                    "seed_mesh_edge_state": action.get("seed_mesh_edge_state"),
                    "seed_mesh_trade_thesis_state": action.get("seed_mesh_trade_thesis_state"),
                    "seed_mesh_opportunity_score": action.get("seed_mesh_opportunity_score"),
                    "seed_mesh_opportunity_decision_band": action.get("seed_mesh_opportunity_decision_band"),
                    "seed_mesh_research_only": action.get("seed_mesh_research_only"),
                    "seed_mesh_execution_allowed": action.get("seed_mesh_execution_allowed"),
                    "research_watchlist_id": action.get("research_watchlist_id"),
                    "priority_band": action.get("research_priority_band"),
                    "priority_score": action.get("research_priority_score"),
                    "priority_reasons": action.get("priority_reasons") or [],
                    "watchlist_scheduler_state": action.get("watchlist_scheduler_state"),
                    "next_refresh_due_at": action.get("next_refresh_due_at"),
                    "score_actionability_cycle_consistent": bool(
                        (not action.get("source_refresh_cycle_id") or not edge.get("source_refresh_cycle_id"))
                        or action.get("source_refresh_cycle_id") == edge.get("source_refresh_cycle_id")
                    ),
                    "same_market_guard_id": action.get("same_market_guard_id") or (action.get("lifecycle_gate_trace") or {}).get("same_market_guard_id"),
                    "exit_plan_id": action.get("exit_plan_id") or (action.get("lifecycle_gate_trace") or {}).get("exit_plan_id"),
                    "actionability_result_id": action.get("actionability_result_id"),
                    "edge_state": edge.get("edge_state"),
                    "risk_decision": edge.get("risk_decision"),
                    "risk_blocker_subtype": edge.get("risk_blocker_subtype"),
                    "risk_capital_classification": risk_capital_trace.get("classification"),
                    "risk_capital_policy_state": action.get("risk_capital_policy_state"),
                    "thesis_id": trade_thesis_trace.get("thesis_id"),
                    "trade_thesis_type": trade_thesis_trace.get("trade_thesis_type"),
                    "exit_intent": trade_thesis_trace.get("exit_intent"),
                    "hold_time_used": trade_thesis_trace.get("hold_time_used_hours"),
                    "hold_time_source": trade_thesis_trace.get("hold_time_source"),
                    "capital_efficiency_comparison": {
                        "original_reward_per_dollar_hour": trade_thesis_trace.get("original_reward_per_dollar_hour"),
                        "dynamic_reward_per_dollar_hour": trade_thesis_trace.get("dynamic_reward_per_dollar_hour"),
                        "dynamic_hold_time_applied": trade_thesis_trace.get("dynamic_hold_time_applied"),
                    },
                    "exit_intent_trace": {
                        "exit_intent": trade_thesis_trace.get("exit_intent"),
                        "status": trade_thesis_trace.get("status"),
                        "blocker_code": trade_thesis_trace.get("blocker_code"),
                    },
                    "exit_classification": action.get("exit_gate_trace", {}).get("classification") if isinstance(action.get("exit_gate_trace"), dict) else None,
                    "exit_readiness_state": action.get("exit_readiness_state"),
                    "small_paper_readiness_result": action.get("candidate_paper_actionability_state"),
                    "opportunity_score_id": opportunity_score.get("opportunity_score_id"),
                    "opportunity_score": opportunity_score.get("overall_score"),
                    "opportunity_score_breakdown": opportunity_score.get("components") or {},
                    "opportunity_decision_band": opportunity_score.get("decision_band"),
                    "paper_observation_eligible": opportunity_score.get("paper_observation_eligible"),
                    "full_paper_certification_ready": opportunity_score.get("full_paper_certification_ready"),
                    "observation_policy_review_id": action.get("paper_observation_policy_review_id") or opportunity_score.get("observation_policy_review_id"),
                    "observation_policy_state": action.get("paper_observation_policy_state") or opportunity_score.get("observation_policy_state"),
                    "observation_allowed_by_policy": bool(action.get("observation_allowed_by_policy") or opportunity_score.get("observation_allowed_by_policy")),
                    "observation_policy_blockers": action.get("observation_policy_blockers") or opportunity_score.get("observation_policy_blockers") or [],
                    "observation_execution_mode_implemented": bool(action.get("observation_execution_mode_implemented") or opportunity_score.get("observation_execution_mode_implemented")),
                    "exact_gate_preventing_phase10": _phase10_gate(action),
                    "actionability_state": action.get("candidate_paper_actionability_state"),
                    "lifecycle_gate_trace": action.get("lifecycle_gate_trace") or {},
                    "risk_capital_gate_trace": action.get("risk_capital_gate_trace") or {},
                    "exit_gate_trace": action.get("exit_gate_trace") or {},
                    "stale_gate_selected": action.get("stale_gate_selected"),
                    "lifecycle_blocker_current": action.get("lifecycle_blocker_current"),
                    "exact_current_lifecycle_blocker": action.get("exact_current_lifecycle_blocker"),
                    "decision_cycle_consistent": action.get("decision_cycle_consistent"),
                    "propagation_breakpoint": action.get("propagation_breakpoint") or _breakpoint(edge),
                    "fresh_sources_used": edge.get("fresh_sources_used") or [],
                    "stale_sources_ignored": edge.get("stale_sources_ignored") or [],
                    "stale_sources_blocking": edge.get("stale_sources_blocking") or [],
                }
            )
        return {
            "status": "REAL" if traces else "MISSING",
            "source": "source_refresh_status + source_backed_edge + paper_actionability",
            "generated_at": now,
            "source_refresh_cycle_id": source_refresh.get("latest_source_refresh_cycle_id") or ((source_refresh.get("latest_cycle") or {}).get("cycle_id")),
            "source_refresh_state": source_refresh.get("source_refresh_orchestrator_state"),
            "propagation_state": source_refresh.get("propagation_state") or ("ACTIVE" if any(item.get("source_refresh_cycle_id") for item in edge_items) else "BLOCKED"),
            "propagation_breakpoint": source_refresh.get("propagation_breakpoint") or (None if traces else "EDGE_THESIS_MISSING"),
            "counts": {
                "traces": len(traces),
                "cycle_consistent": sum(1 for item in traces if item.get("decision_cycle_consistent") is True),
                "missing_source_refresh_context": sum(1 for item in traces if not item.get("source_refresh_cycle_id")),
            },
            "traces": traces,
            "errors": [],
            "warnings": [] if traces else ["No decision propagation traces are available yet."],
        }


def _breakpoint(edge: dict[str, Any]) -> str | None:
    if not edge.get("source_refresh_cycle_id"):
        return "SOURCE_REFRESH_CONTEXT_MISSING"
    if not edge.get("edge_thesis_id"):
        return "EDGE_THESIS_ID_MISSING"
    if not edge.get("risk_evidence_id"):
        return "RISK_EVIDENCE_ID_MISSING"
    return None


def _phase10_gate(action: dict[str, Any]) -> str | None:
    state = action.get("candidate_paper_actionability_state")
    if state == "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED":
        return "PAPER_SIMULATION_OFF_EXPECTED"
    if state == "BLOCKED_BY_RISK":
        trace = action.get("risk_capital_gate_trace") if isinstance(action.get("risk_capital_gate_trace"), dict) else {}
        return trace.get("risk_capital_blocker") or action.get("risk_gate_state") or "BLOCKED_BY_RISK_CURRENT"
    if state == "BLOCKED_BY_EXIT":
        trace = action.get("exit_gate_trace") if isinstance(action.get("exit_gate_trace"), dict) else {}
        return trace.get("status") or "BLOCKED_BY_EXIT_CURRENT"
    if state == "BLOCKED_BY_CAPITAL":
        return action.get("capital_gate_state") or "BLOCKED_BY_CAPITAL_CURRENT"
    return state
