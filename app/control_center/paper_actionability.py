from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.control_center.orderbook_price_readiness import CandidatePricePathService
from app.control_center.pre_paper_active_truth import pre_paper_active_counts
from app.control_center.paper_simulation import PaperSimulationControlService
from app.control_center.source_backed_edge import SourceBackedEdgeControlService
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
from app.services.market_universe_memory import MarketUniverseMemoryService
from app.services.paper_observation_policy import PaperObservationPolicyReviewService
from app.services.proactive_candidate_generation import ProactiveCandidateGenerationService
from app.services.research_priority_watchlist import ResearchPriorityWatchlistService
from app.services.source_event_memory import SourceEventMemoryService
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService
from app.services.trade_opportunity_score import attach_opportunity_score, summarize_opportunity_scores


ACTIONABLE_STATES = {
    "ACTIONABLE_SMALL_PAPER",
    "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
    "NOT_ACTIONABLE_INCOMPLETE_TRACE",
    "NOT_ACTIONABLE_EVENT_SCOPE",
    "NOT_ACTIONABLE_TOKEN_SIDE_MISMATCH",
    "NOT_ACTIONABLE_RISK_REVIEW",
    "NOT_ACTIONABLE_RISK_BLOCKED",
    "NOT_ACTIONABLE_MISSING_TRADE_THESIS",
    "NOT_ACTIONABLE_MISSING_TRADE_THESIS_LINK",
    "NOT_ACTIONABLE_MISSING_EXIT_INTENT",
    "NOT_ACTIONABLE_MISSING_DYNAMIC_HOLD_TIME",
    "NOT_ACTIONABLE_EXIT_NOT_READY",
    "NOT_ACTIONABLE_CAPITAL_BLOCKED",
    "NOT_ACTIONABLE_LIFECYCLE_NOT_ALLOWED",
    "NOT_ACTIONABLE_STALE_EVIDENCE",
    "NOT_ACTIONABLE_DUPLICATE_OR_OPEN_POSITION_CONFLICT",
    "WATCH_FOR_CONFIRMATION",
    "WAITING_FOR_PRICE_REFRESH",
    "WAITING_FOR_LIFECYCLE",
    "WAITING_FOR_CAPITAL",
    "BLOCKED_BY_RISK",
    "BLOCKED_BY_EXIT",
    "BLOCKED_BY_CAPITAL",
    "BLOCKED_BY_LIFECYCLE",
    "BLOCKED_BY_DATA",
    "BLOCKED_BY_GOVERNOR",
    "BLOCKED_BY_RUNTIME",
    "BLOCKED_BY_PAPER_SIMULATION",
    "NO_TRADE",
    "UNKNOWN",
}


class PaperActionabilityService:
    """Read-only Coordinator-to-Paper actionability contract."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_actionability(self, *, limit: int = 50, offset: int = 0, candidate_id: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        bundles = MeshEvidenceBundleService(connection_factory=self._factory).list_bundles(
            limit=limit,
            offset=offset,
            candidate_id=candidate_id,
            include_opinions=True,
            include_conflicts=True,
        )
        data = dict(bundles.get("data") or bundles)
        paper_simulation_enabled = self._paper_simulation_enabled()
        safety = self._safety_counts()
        source_refresh = self._source_refresh_status()
        items = [
            self._item(
                bundle,
                paper_simulation_enabled=paper_simulation_enabled,
                duplicate_active_intent_risk=safety["duplicate_active_intent_risk"] > 0,
                open_paper_position_conflict=safety["open_paper_positions"] > 0,
            )
            for bundle in data.get("items") or []
        ]
        counts = {
            "items_checked": len(items),
            "candidate_scoped_bundles": sum(1 for item in items if item["candidate_event_actionability_scope"] == "CANDIDATE_SCOPED"),
            "actionable_small_paper": sum(1 for item in items if item["candidate_paper_actionability_state"] == "ACTIONABLE_SMALL_PAPER"),
            "actionable_if_paper_enabled": sum(1 for item in items if item["candidate_paper_actionability_state"] == "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"),
            "watch_for_confirmation": sum(1 for item in items if item["candidate_paper_actionability_state"] == "WATCH_FOR_CONFIRMATION"),
            "waiting_for_price_refresh": sum(1 for item in items if item["candidate_paper_actionability_state"] == "WAITING_FOR_PRICE_REFRESH"),
            "waiting_for_lifecycle": sum(1 for item in items if item["candidate_paper_actionability_state"] == "WAITING_FOR_LIFECYCLE"),
            "waiting_for_capital": sum(1 for item in items if item["candidate_paper_actionability_state"] == "WAITING_FOR_CAPITAL"),
            "waiting_for_risk": sum(1 for item in items if item["candidate_paper_actionability_state"] == "WAITING_FOR_RISK"),
            "waiting_for_exit": sum(1 for item in items if item["candidate_paper_actionability_state"] == "WAITING_FOR_EXIT"),
            "blocked_by_lifecycle": sum(1 for item in items if item["candidate_paper_actionability_state"] == "BLOCKED_BY_LIFECYCLE"),
            "blocked_by_capital": sum(1 for item in items if item["candidate_paper_actionability_state"] == "BLOCKED_BY_CAPITAL"),
            "blocked_by_risk": sum(1 for item in items if item["candidate_paper_actionability_state"] == "BLOCKED_BY_RISK"),
            "blocked_by_exit": sum(1 for item in items if item["candidate_paper_actionability_state"] == "BLOCKED_BY_EXIT"),
            "blocked_by_duplicate": sum(1 for item in items if item["candidate_paper_actionability_state"] == "BLOCKED_BY_DUPLICATE"),
            "blocked_by_open_position": sum(1 for item in items if item["candidate_paper_actionability_state"] == "BLOCKED_BY_OPEN_POSITION"),
            "blocked_by_data": sum(1 for item in items if item["candidate_paper_actionability_state"] == "BLOCKED_BY_DATA"),
            "strict_not_actionable": sum(1 for item in items if str(item["candidate_paper_actionability_state"]).startswith("NOT_ACTIONABLE_")),
            "no_trade": sum(1 for item in items if item["candidate_paper_actionability_state"] == "NO_TRADE"),
            "unknown": sum(1 for item in items if item["candidate_paper_actionability_state"] == "UNKNOWN"),
        }
        score_counts = summarize_opportunity_scores(items)
        observation_policy_counts = (PaperObservationPolicyReviewService(connection_factory=self._factory).summary(limit=5).get("counts") or {})
        counts.update(
            {
                "full_paper_certification_ready": score_counts["full_paper_certification"],
                "paper_observation_eligible": score_counts["paper_observation_eligible"],
                "watch_only": score_counts["watch_only"],
                "opportunity_hard_blocked": score_counts["hard_blocked"],
                "observation_policy_eligible": int(observation_policy_counts.get("observation_policy_eligible_count") or 0),
                "observation_policy_watch": int(observation_policy_counts.get("observation_policy_watch_count") or 0),
                "observation_policy_blocked": int(observation_policy_counts.get("observation_policy_blocked_count") or 0),
                "observation_policy_incomplete": int(observation_policy_counts.get("observation_policy_incomplete_count") or 0),
            }
        )
        candidate_actionability_exists = counts["actionable_small_paper"] + counts["actionable_if_paper_enabled"] + counts["watch_for_confirmation"] > 0
        payload = {
            "status": "REAL" if counts["items_checked"] else "MISSING",
            "source": {
                "mesh_evidence_bundles": "event_log + brain_outputs + coordinator_decisions",
                "candidate_price_path": "orderbook_price_readiness",
                "paper_simulation": "paper_simulation_status",
                "safety_counts": "paper_intents + paper_positions",
                "source_refresh": "source_refresh_status",
            },
            "last_updated": data.get("last_updated") or now.isoformat(),
            "freshness_state": data.get("freshness_state") or "MISSING",
            "readiness_state": "READY" if counts["actionable_small_paper"] or counts["actionable_if_paper_enabled"] else "PARTIAL" if counts["items_checked"] else "UNKNOWN",
            "truth_state": data.get("truth_state") or "UNKNOWN",
            "counts": counts,
            "candidate_actionability_exists": candidate_actionability_exists,
            "paper_simulation_enabled": paper_simulation_enabled,
            "safety_counts": safety,
            "source_refresh_state": source_refresh.get("source_refresh_orchestrator_state"),
            "source_refresh_counts": source_refresh.get("counts") or {},
            "stale_source_blockers": source_refresh.get("stale_sources") or [],
            "missing_source_blockers": (source_refresh.get("missing_config_sources") or []) + (source_refresh.get("no_connector_sources") or []),
            "items": items,
            "blockers": _top_blockers(items),
            "unified_blockers": _top_unified_blockers(items),
            "warnings": [] if candidate_actionability_exists else ["No candidate currently satisfies candidate-level paper actionability."],
            "errors": [],
            "generated_at": now.isoformat(),
        }
        return _envelope(payload)

    def _item(
        self,
        bundle: dict[str, Any],
        *,
        paper_simulation_enabled: bool,
        duplicate_active_intent_risk: bool,
        open_paper_position_conflict: bool,
    ) -> dict[str, Any]:
        candidate_id = bundle.get("candidate_id")
        price = self._candidate_price(candidate_id) if candidate_id else {}
        edge = self._latest_edge(candidate_id)
        lifecycle_gate_trace = self._latest_lifecycle_gate_trace(candidate_id)
        source_refresh_cycle_id = (
            edge.get("source_refresh_cycle_id")
            or lifecycle_gate_trace.get("source_refresh_cycle_id")
            or (edge.get("propagation_context") or {}).get("source_refresh_cycle_id")
        )
        trade_thesis = self._latest_trade_thesis(
            candidate_id,
            side=bundle.get("side"),
            token_id=bundle.get("token_id"),
            source_refresh_cycle_id=source_refresh_cycle_id,
        )
        market_memory = self._market_memory_fields(
            market_id=bundle.get("market_id"),
            token_id=bundle.get("token_id"),
        )
        source_event_memory = self._source_event_memory_fields(market_id=bundle.get("market_id"))
        targeted_revalidation = self._targeted_revalidation_fields(market_id=bundle.get("market_id"))
        proactive_seed = self._proactive_candidate_seed_fields(market_id=bundle.get("market_id"))
        observation_policy = self._observation_policy_fields(proactive_seed_id=proactive_seed.get("latest_proactive_candidate_seed_id"))
        research_priority = self._research_priority_fields(market_id=bundle.get("market_id"))
        state, operational_state, confidence, blockers, required, next_state = _map_actionability(
            bundle,
            price,
            edge=edge,
            paper_simulation_enabled=paper_simulation_enabled,
            duplicate_active_intent_risk=duplicate_active_intent_risk,
            open_paper_position_conflict=open_paper_position_conflict,
        )
        state, operational_state, confidence, blockers, required, next_state = _reconcile_lifecycle_gate_actionability(
            state,
            operational_state,
            confidence,
            blockers,
            required,
            next_state,
            lifecycle_gate_trace,
            edge=edge,
            paper_simulation_enabled=paper_simulation_enabled,
            duplicate_active_intent_risk=duplicate_active_intent_risk,
            open_paper_position_conflict=open_paper_position_conflict,
        )
        opinions = _opinion_summary(bundle.get("opinions") or {})
        risk_capital_trace = lifecycle_gate_trace.get("risk_capital_gate_trace") or {}
        trace_thesis = risk_capital_trace.get("trade_thesis_trace") if isinstance(risk_capital_trace.get("trade_thesis_trace"), dict) else {}
        trade_thesis_type = risk_capital_trace.get("trade_thesis_type") or trace_thesis.get("trade_thesis_type") or trade_thesis.get("trade_thesis_type")
        exit_intent = risk_capital_trace.get("exit_intent") or trace_thesis.get("exit_intent") or trade_thesis.get("exit_intent")
        expected_hold_time_hours = risk_capital_trace.get("expected_hold_time_hours") or trace_thesis.get("expected_hold_time_hours") or trace_thesis.get("hold_time_used_hours") or trade_thesis.get("expected_hold_time_hours")
        hold_time_source = risk_capital_trace.get("hold_time_source") or trace_thesis.get("hold_time_source") or trade_thesis.get("hold_time_source")
        thesis_id = trace_thesis.get("thesis_id") or trade_thesis.get("thesis_id")
        price_orderbook = price.get("orderbook") if isinstance(price.get("orderbook"), dict) else {}
        selected_orderbook_snapshot_id = (
            price_orderbook.get("orderbook_snapshot_id")
            or price.get("orderbook_snapshot_id")
            or lifecycle_gate_trace.get("orderbook_snapshot_id")
        )
        item = {
            "candidate_id": candidate_id,
            "market_id": bundle.get("market_id"),
            "side": bundle.get("side"),
            "token_id": bundle.get("token_id"),
            "event_id": bundle.get("event_id"),
            "selected_candidate_event_id": bundle.get("event_id"),
            "correlation_id": bundle.get("correlation_id"),
            "mesh_bundle_id": bundle.get("bundle_id"),
            "candidate_event_scope": "CANDIDATE_SCOPED" if bundle.get("candidate_event_actionability_scope") == "CANDIDATE_SCOPED" else bundle.get("candidate_event_actionability_scope"),
            "candidate_event_link_state": bundle.get("candidate_event_link_state"),
            "candidate_event_actionability_scope": bundle.get("candidate_event_actionability_scope"),
            "correlation_confidence": bundle.get("correlation_confidence"),
            "candidate_price_path_state": price.get("candidate_price_path_state") or price.get("price_path_state"),
            "candidate_trusted_orderbook_state": price.get("candidate_trusted_orderbook_state") or price.get("trusted_orderbook_state"),
            "orderbook_freshness_state": price.get("candidate_trusted_orderbook_state") or price.get("candidate_price_path_state") or price.get("trusted_orderbook_state") or price.get("price_path_state"),
            "selected_orderbook_snapshot_id": selected_orderbook_snapshot_id,
            "candidate_price_orderbook_snapshot_id": selected_orderbook_snapshot_id,
            "coordinator_decision": (bundle.get("coordinator") or {}).get("decision"),
            "mesh_consensus_state": bundle.get("mesh_consensus_state"),
            "candidate_paper_actionability_state": state,
            "paper_actionability_state": state,
            "operational_paper_execution_state": operational_state,
            "actionability_confidence": confidence,
            "opinions": opinions,
            "edge_thesis": edge,
            "lifecycle_gate_trace": lifecycle_gate_trace,
            "exact_current_lifecycle_blocker": lifecycle_gate_trace.get("exact_current_lifecycle_blocker"),
            "stale_gate_selected": lifecycle_gate_trace.get("stale_gate_selected"),
            "lifecycle_blocker_current": lifecycle_gate_trace.get("lifecycle_blocker_current"),
            "risk_gate_state": lifecycle_gate_trace.get("risk_gate_state"),
            "capital_gate_state": lifecycle_gate_trace.get("capital_gate_state"),
            "orderbook_gate_state": lifecycle_gate_trace.get("orderbook_gate_state"),
            "same_market_gate_state": lifecycle_gate_trace.get("same_market_gate_state"),
            "exit_gate_state": lifecycle_gate_trace.get("exit_gate_state"),
            "risk_capital_gate_trace": risk_capital_trace,
            "trade_thesis_trace": trace_thesis,
            "joined_trade_thesis": trade_thesis,
            "thesis_id": thesis_id,
            "trade_thesis_type": trade_thesis_type,
            "exit_intent": exit_intent,
            "expected_hold_time_hours": expected_hold_time_hours,
            "hold_time_source": hold_time_source,
            "dynamic_rpdh": risk_capital_trace.get("dynamic_reward_per_dollar_hour") or trace_thesis.get("dynamic_reward_per_dollar_hour"),
            "capital_efficiency_before_thesis": trace_thesis.get("capital_efficiency_before_thesis"),
            "capital_efficiency_after_thesis": trace_thesis.get("capital_efficiency_after_thesis") or risk_capital_trace.get("capital_efficiency_score"),
            "exit_gate_trace": lifecycle_gate_trace.get("exit_gate_trace") or {},
            "risk_capital_policy_state": risk_capital_trace.get("risk_capital_policy_state"),
            "exit_readiness_state": (lifecycle_gate_trace.get("exit_gate_trace") or {}).get("status"),
            "propagation_context": edge.get("propagation_context") or {},
            "source_refresh_cycle_id": edge.get("source_refresh_cycle_id"),
            "edge_thesis_id": edge.get("edge_thesis_id"),
            "risk_evidence_id": edge.get("risk_evidence_id"),
            "lifecycle_decision_id": lifecycle_gate_trace.get("lifecycle_decision_id"),
            "capital_evidence_id": lifecycle_gate_trace.get("capital_evidence_id"),
            "orderbook_snapshot_id": lifecycle_gate_trace.get("orderbook_snapshot_id") or selected_orderbook_snapshot_id,
            "same_market_guard_id": lifecycle_gate_trace.get("same_market_guard_id"),
            "exit_plan_id": lifecycle_gate_trace.get("exit_plan_id"),
            "actionability_result_id": lifecycle_gate_trace.get("lifecycle_decision_id"),
            "decision_cycle_consistent": _decision_cycle_consistent(edge, lifecycle_gate_trace),
            **market_memory,
            **source_event_memory,
            **targeted_revalidation,
            **proactive_seed,
            **observation_policy,
            **research_priority,
            "source_refresh_to_actionability_latency_seconds": _source_refresh_latency_seconds(edge),
            "propagation_breakpoint": _propagation_breakpoint(edge, state, lifecycle_gate_trace),
            "edge_state": edge.get("edge_state"),
            "edge_score": edge.get("edge_score"),
            "source_backed": edge.get("source_backed"),
            "risk_usable": edge.get("risk_usable"),
            "fresh_sources_used": edge.get("fresh_sources_used") or [],
            "stale_sources_ignored": edge.get("stale_sources_ignored") or [],
            "stale_sources_blocking": edge.get("stale_sources_blocking") or [],
            "derived_signals_used": edge.get("derived_signals_used") or [],
            "supporting_neurons": edge.get("supporting_neurons") or [],
            "opposing_neurons": edge.get("opposing_neurons") or [],
            "full_mesh_inquiry_state": "READY" if edge.get("risk_usable") is True else "BLOCKED" if edge else "MISSING",
            "full_mesh_edge_state": edge.get("edge_state"),
            "full_mesh_required_to_pass": edge.get("required_to_pass") or [],
            "source_organs_status": edge.get("source_organ_status") or {},
            "source_organs_queried": edge.get("source_organs_queried") or 0,
            "source_organs_unavailable": edge.get("source_organs_unavailable") or [],
            "source_organs_no_data": edge.get("source_organs_no_data") or [],
            "missing_source_organs": edge.get("missing_source_organs") or [],
            "directional_sources_found": edge.get("directional_sources_found") or 0,
            "execution_allowed": False,
            "would_require_paper_simulation_on": state in {"ACTIONABLE_SMALL_PAPER", "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"},
            "blockers": blockers,
            "unified_blockers": unified_blockers(
                blockers,
                source="paper_actionability",
                candidate_id=candidate_id,
                event_id=bundle.get("event_id"),
                correlation_id=bundle.get("correlation_id"),
                market_id=bundle.get("market_id"),
                side=bundle.get("side"),
                token_id=bundle.get("token_id"),
            ),
            "required_to_pass": required,
            "next_possible_state": next_state,
            "operator_summary": _summary(state, operational_state, blockers),
        }
        return attach_opportunity_score(_reconcile_strict_actionability(item, paper_simulation_enabled=paper_simulation_enabled))

    def _candidate_price(self, candidate_id: str | None) -> dict[str, Any]:
        if not candidate_id:
            return {}
        try:
            payload = CandidatePricePathService(connection_factory=self._factory).get_candidate(str(candidate_id))
        except Exception:
            return {}
        data = payload.get("data") if isinstance(payload, dict) else None
        return dict((data or payload or {}).get("candidate") or {})

    def _paper_simulation_enabled(self) -> bool:
        try:
            payload = PaperSimulationControlService(connection_factory=self._factory).status()
        except Exception:
            return False
        return bool((payload.get("data") or payload).get("enabled"))

    def _observation_policy_fields(self, *, proactive_seed_id: str | None) -> dict[str, Any]:
        try:
            return PaperObservationPolicyReviewService(connection_factory=self._factory).fields_for_seed(proactive_candidate_seed_id=proactive_seed_id)
        except Exception:
            return {
                "paper_observation_policy_review_id": None,
                "paper_observation_policy_state": "NOT_REVIEWED",
                "observation_allowed_by_policy": False,
                "observation_execution_mode_implemented": False,
                "observation_paper_intent_creation_allowed": False,
                "observation_policy_execution_allowed": False,
                "observation_policy_paper_allowed": False,
            }

    def _latest_edge(self, candidate_id: str | None) -> dict[str, Any]:
        if not candidate_id:
            return {}
        try:
            payload = SourceBackedEdgeControlService(connection_factory=self._factory).list_edges(limit=1, candidate_id=str(candidate_id))
        except Exception:
            return {}
        items = payload.get("items") or []
        return dict(items[0]) if items else {}

    def _safety_counts(self) -> dict[str, int]:
        out = {"duplicate_active_intent_risk": 0, "open_paper_positions": 0}
        if not self._factory.enabled:
            return out
        with self._factory.connect() as conn:
            out.update(pre_paper_active_counts(conn))
        return out

    def _source_refresh_status(self) -> dict[str, Any]:
        try:
            from app.control_center.source_refresh_status import SourceRefreshStatusService

            return SourceRefreshStatusService(connection_factory=self._factory).get_status()
        except Exception as exc:
            return {"source_refresh_orchestrator_state": "UNKNOWN", "counts": {}, "stale_sources": [], "missing_config_sources": [], "no_connector_sources": [], "error": f"{type(exc).__name__}: {exc}"}

    def _market_memory_fields(self, *, market_id: str | None, token_id: str | None) -> dict[str, Any]:
        try:
            return MarketUniverseMemoryService(connection_factory=self._factory).lookup_fields(
                market_id=str(market_id) if market_id else None,
                token_id=str(token_id) if token_id else None,
            )
        except Exception as exc:
            return {
                "market_memory_id": None,
                "market_memory_status": "UNKNOWN",
                "market_memory_freshness": "UNKNOWN",
                "market_identity_verification_state": "UNKNOWN",
                "token_verification_state": "UNKNOWN",
                "market_memory_error": f"{type(exc).__name__}: {exc}",
            }

    def _source_event_memory_fields(self, *, market_id: str | None) -> dict[str, Any]:
        try:
            return SourceEventMemoryService(connection_factory=self._factory).link_fields_for_market(
                market_id=str(market_id) if market_id else None
            )
        except Exception as exc:
            return {
                "recent_source_event_count": 0,
                "strongest_event_link_type": None,
                "strongest_event_link_confidence": 0.0,
                "recent_directional_event_state": "UNKNOWN",
                "recent_source_event_link_state": "EVENT_NOT_LINKED",
                "direct_event_link_count": 0,
                "likely_event_link_count": 0,
                "source_event_memory_ids": [],
                "event_to_market_link_ids": [],
                "source_event_memory_error": f"{type(exc).__name__}: {exc}",
            }

    def _targeted_revalidation_fields(self, *, market_id: str | None) -> dict[str, Any]:
        try:
            return TargetedMarketRevalidationService(connection_factory=self._factory).fields_for_market(
                market_id=str(market_id) if market_id else None
            )
        except Exception as exc:
            return {
                "targeted_revalidation_id": None,
                "latest_targeted_revalidation_state": "UNKNOWN",
                "orderbook_refresh_state_from_revalidation": "UNKNOWN",
                "movement_state_from_revalidation": "UNKNOWN",
                "already_priced_in_state_from_revalidation": "UNKNOWN",
                "revalidation_candidate_generation_later_state": "UNKNOWN",
                "candidate_generation_later_eligible": False,
                "targeted_revalidation_error": f"{type(exc).__name__}: {exc}",
            }

    def _proactive_candidate_seed_fields(self, *, market_id: str | None) -> dict[str, Any]:
        try:
            return ProactiveCandidateGenerationService(connection_factory=self._factory).fields_for_market(
                market_id=str(market_id) if market_id else None
            )
        except Exception as exc:
            return {
                "proactive_candidate_seed_count": 0,
                "generated_seed_count": 0,
                "watch_only_seed_count": 0,
                "latest_proactive_seed_at": None,
                "latest_seed_state": "UNKNOWN",
                "proactive_seed_id": None,
                "research_only": None,
                "seed_execution_allowed": False,
                "seed_paper_allowed": False,
                "seed_shadow_allowed": False,
                "seed_live_allowed": False,
                "mesh_handoff_state": "UNKNOWN",
                "proactive_candidate_seed_error": f"{type(exc).__name__}: {exc}",
            }

    def _research_priority_fields(self, *, market_id: str | None) -> dict[str, Any]:
        try:
            return ResearchPriorityWatchlistService(connection_factory=self._factory).fields_for_market(
                market_id=str(market_id) if market_id else None
            )
        except Exception as exc:
            return {
                "research_watchlist_id": None,
                "research_priority_band": None,
                "research_priority_score": None,
                "next_refresh_due_at": None,
                "watchlist_reason": None,
                "research_priority_error": f"{type(exc).__name__}: {exc}",
            }

    def _latest_trade_thesis(self, candidate_id: str | None, *, side: str | None, token_id: str | None, source_refresh_cycle_id: str | None) -> dict[str, Any]:
        if not candidate_id or not side or not token_id or not source_refresh_cycle_id or not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "trade_thesis_evaluations"):
                return {}
            row = conn.execute(
                """
                SELECT thesis_id, candidate_id, subject_id, market_id, side, token_id,
                       source_refresh_cycle_id, edge_thesis_id, risk_evidence_id,
                       trade_thesis_type, exit_intent, status, blocker_code,
                       expected_hold_time_hours, hold_time_source, target_exit_price,
                       thesis_confidence, exit_confidence, ai_review_state, created_at
                FROM trade_thesis_evaluations
                WHERE candidate_id=%s
                  AND side=%s
                  AND token_id=%s
                  AND source_refresh_cycle_id=%s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (str(candidate_id), str(side), str(token_id), str(source_refresh_cycle_id)),
            ).fetchone()
        if not row:
            return {}
        out = dict(row)
        if hasattr(out.get("created_at"), "isoformat"):
            out["created_at"] = out["created_at"].isoformat()
        return out

    def _latest_lifecycle_gate_trace(self, candidate_id: str | None) -> dict[str, Any]:
        if not candidate_id or not self._factory.enabled:
            return {}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "lifecycle_governance_decisions"):
                return {}
            row = conn.execute(
                """
                SELECT *
                FROM lifecycle_governance_decisions
                WHERE subject_type IN ('PAPER_CANDIDATE','FRESH_SEED') AND subject_id=%s
                ORDER BY created_at DESC,id DESC
                LIMIT 1
                """,
                (str(candidate_id),),
            ).fetchone()
            if not row:
                return {}
            decision = dict(row)
            plan = None
            if decision.get("lifecycle_plan_id") and _table_exists(conn, "trade_lifecycle_plans"):
                plan_row = conn.execute(
                    "SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s LIMIT 1",
                    (decision.get("lifecycle_plan_id"),),
                ).fetchone()
                plan = dict(plan_row) if plan_row else None
        return _lifecycle_gate_trace(decision, plan)


def _map_actionability(
    bundle: dict[str, Any],
    price: dict[str, Any],
    *,
    edge: dict[str, Any] | None = None,
    paper_simulation_enabled: bool = True,
    duplicate_active_intent_risk: bool = False,
    open_paper_position_conflict: bool = False,
) -> tuple[str, str, str, list[str], list[str], str]:
    blockers: list[str] = []
    candidate_scoped = bundle.get("candidate_event_actionability_scope") == "CANDIDATE_SCOPED"
    high_confidence = bundle.get("correlation_confidence") == "HIGH"
    if bundle.get("candidate_event_actionability_scope") != "CANDIDATE_SCOPED" or bundle.get("correlation_confidence") != "HIGH":
        blockers.append("MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE" if bundle.get("candidate_event_actionability_scope") == "MARKET_SCOPED_ONLY" else "MISSING_CANDIDATE_EVENT_LINK")
    price_state = price.get("candidate_price_path_state") or price.get("price_path_state")
    if price_state and price_state != "CANDIDATE_PRICE_READY" and price_state != "PRICE_READY":
        blockers.append("WAITING_FOR_PRICE_REFRESH" if "STALE" in str(price_state) or "REFRESH" in str(price_state) else "BLOCKED_BY_DATA")
    if bundle.get("bundle_state") in {"PARTIAL", "MISSING", "STALE"}:
        blockers.append("BLOCKED_BY_DATA")
    opinions = bundle.get("opinions") or {}
    _append_opinion_blockers(blockers, opinions)
    coordinator = bundle.get("coordinator") or {}
    decision = str(coordinator.get("decision") or "")
    if decision == "LIFECYCLE_BLOCKED":
        blockers.append("BLOCKED_BY_LIFECYCLE")
    elif decision == "CAPITAL_BLOCKED":
        blockers.append("BLOCKED_BY_CAPITAL")
    elif decision == "WAITING_FOR_LIFECYCLE":
        blockers.append("WAITING_FOR_LIFECYCLE")
    elif decision == "WAITING_FOR_CAPITAL":
        blockers.append("WAITING_FOR_CAPITAL")
    elif decision == "PRICE_BLOCKED":
        blockers.append("WAITING_FOR_PRICE_REFRESH")
    elif decision in {"CONFLICT", "NO_ACTION"}:
        blockers.append("NO_TRADE")
    elif decision == "WAITING_FOR_EVIDENCE":
        blockers.append("BLOCKED_BY_DATA")
    if bundle.get("conflicts") and not _has_specific_hard_block(blockers):
        blockers.append("NO_TRADE")
    edge = edge or {}
    if edge and edge.get("risk_usable") is not True:
        blockers.append("BLOCKED_BY_RISK")
        edge_blocker = str(edge.get("blocker_code") or edge.get("edge_state") or "")
        if edge_blocker and edge_blocker not in {"None", "null"}:
            blockers.append(edge_blocker)
    if duplicate_active_intent_risk and candidate_scoped:
        blockers.append("BLOCKED_BY_DUPLICATE")
    if open_paper_position_conflict and candidate_scoped:
        blockers.append("BLOCKED_BY_OPEN_POSITION")
    blockers = _unique(blockers)
    confidence = "HIGH" if candidate_scoped and high_confidence else "LOW" if blockers else "MEDIUM"
    operational_state = "EXECUTION_DISABLED_PAPER_OFF" if not paper_simulation_enabled else "EXECUTION_NOT_READY"
    if not blockers and decision == "PRICE_READY":
        if paper_simulation_enabled:
            return "ACTIONABLE_SMALL_PAPER", "EXECUTION_READY_IF_ENABLED", "HIGH", [], ["All candidate-scoped mesh gates are satisfied; execution remains controlled by Phase 10 paper certification."], "READY_FOR_PAPER_CERTIFICATION"
        return "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED", "EXECUTION_DISABLED_PAPER_OFF", "HIGH", ["PAPER_SIMULATION_OFF"], _required(["PAPER_SIMULATION_OFF"]), "ENABLE_PAPER_SIMULATION_IN_PHASE_10_ONLY"
    if "WAITING_FOR_LIFECYCLE" in blockers:
        return _state_with_operational("WAITING_FOR_LIFECYCLE", operational_state, confidence, blockers)
    if "WAITING_FOR_CAPITAL" in blockers:
        return _state_with_operational("WAITING_FOR_CAPITAL", operational_state, confidence, blockers)
    if "WAITING_FOR_RISK" in blockers:
        return _state_with_operational("WAITING_FOR_RISK", operational_state, confidence, blockers)
    if "WAITING_FOR_EXIT" in blockers:
        return _state_with_operational("WAITING_FOR_EXIT", operational_state, confidence, blockers)
    if "BLOCKED_BY_LIFECYCLE" in blockers:
        return _state_with_operational("BLOCKED_BY_LIFECYCLE", operational_state, confidence, blockers)
    if "BLOCKED_BY_CAPITAL" in blockers:
        return _state_with_operational("BLOCKED_BY_CAPITAL", operational_state, confidence, blockers)
    if "BLOCKED_BY_RISK" in blockers:
        return _state_with_operational("BLOCKED_BY_RISK", operational_state, confidence, blockers)
    if "BLOCKED_BY_EXIT" in blockers:
        return _state_with_operational("BLOCKED_BY_EXIT", operational_state, confidence, blockers)
    if "WAITING_FOR_PRICE_REFRESH" in blockers:
        return _state_with_operational("WAITING_FOR_PRICE_REFRESH", operational_state, confidence, blockers)
    if "BLOCKED_BY_DATA" in blockers or "MISSING_CANDIDATE_EVENT_LINK" in blockers or "MARKET_LEVEL_EVENT_NOT_CANDIDATE_ACTIONABLE" in blockers:
        return _state_with_operational("BLOCKED_BY_DATA", operational_state, confidence, blockers)
    if "BLOCKED_BY_DUPLICATE" in blockers or "BLOCKED_BY_OPEN_POSITION" in blockers:
        return _state_with_operational("BLOCKED_BY_DUPLICATE" if "BLOCKED_BY_DUPLICATE" in blockers else "BLOCKED_BY_OPEN_POSITION", operational_state if not paper_simulation_enabled else "EXECUTION_DISABLED_SAFETY", confidence, blockers)
    if "NO_TRADE" in blockers:
        return _state_with_operational("NO_TRADE", operational_state, confidence, blockers)
    return _state_with_operational("WATCH_FOR_CONFIRMATION", operational_state, confidence, blockers)


def _state_with_operational(state: str, operational: str, confidence: str, blockers: list[str]) -> tuple[str, str, str, list[str], list[str], str]:
    next_state = {
        "BLOCKED_BY_LIFECYCLE": "WAITING_FOR_LIFECYCLE_CLEARANCE",
        "WAITING_FOR_LIFECYCLE": "WAIT_FOR_FRESH_LIFECYCLE_OPINION",
        "BLOCKED_BY_CAPITAL": "WAITING_FOR_CAPITAL_CLEARANCE",
        "WAITING_FOR_CAPITAL": "WAIT_FOR_FRESH_CAPITAL_OPINION",
        "BLOCKED_BY_RISK": "WAITING_FOR_RISK_CLEARANCE",
        "WAITING_FOR_RISK": "WAIT_FOR_FRESH_RISK_OPINION",
        "BLOCKED_BY_EXIT": "WAITING_FOR_EXIT_CLEARANCE",
        "WAITING_FOR_EXIT": "WAIT_FOR_FRESH_EXIT_OPINION",
        "WAITING_FOR_PRICE_REFRESH": "REFRESH_CANDIDATE_PRICE_PATH",
        "BLOCKED_BY_DUPLICATE": "RESOLVE_DUPLICATE_ACTIVE_INTENT",
        "BLOCKED_BY_OPEN_POSITION": "RESOLVE_OPEN_PAPER_POSITION_CONFLICT",
        "BLOCKED_BY_DATA": "REFRESH_CANDIDATE_SCOPED_EVIDENCE",
        "NO_TRADE": "KEEP_OBSERVING",
    }.get(state, "WATCH_FOR_CONFIRMATION")
    return state, operational, confidence, blockers, _required(blockers), next_state


def _reconcile_lifecycle_gate_actionability(
    state: str,
    operational_state: str,
    confidence: str,
    blockers: list[str],
    required: list[str],
    next_state: str,
    lifecycle_gate_trace: dict[str, Any],
    *,
    edge: dict[str, Any],
    paper_simulation_enabled: bool,
    duplicate_active_intent_risk: bool,
    open_paper_position_conflict: bool,
) -> tuple[str, str, str, list[str], list[str], str]:
    """Prefer the latest candidate lifecycle gate trace over stale bundle windows.

    Mesh bundle rows are still useful context, but they can lag behind the
    DATA_ONLY lifecycle reconciliation. A candidate can only be promoted here
    when the latest lifecycle decision and the latest Edge/Risk thesis agree on
    the same candidate and have no current critical gate blockers.
    """

    if not lifecycle_gate_trace:
        return state, operational_state, confidence, blockers, required, next_state
    if duplicate_active_intent_risk:
        return _state_with_operational("BLOCKED_BY_DUPLICATE", "EXECUTION_DISABLED_SAFETY", confidence, _unique([*blockers, "BLOCKED_BY_DUPLICATE"]))
    if open_paper_position_conflict:
        return _state_with_operational("BLOCKED_BY_OPEN_POSITION", "EXECUTION_DISABLED_SAFETY", confidence, _unique([*blockers, "BLOCKED_BY_OPEN_POSITION"]))

    critical = [str(item).upper() for item in lifecycle_gate_trace.get("critical_blockers") or []]
    if critical:
        mapped = _state_from_current_lifecycle_blockers(critical)
        exact = lifecycle_gate_trace.get("exact_current_lifecycle_blocker")
        merged = _unique([mapped, *(critical if exact else blockers)])
        return _state_with_operational(mapped, operational_state, "HIGH" if lifecycle_gate_trace.get("lifecycle_blocker_current") else confidence, merged)

    if not _lifecycle_gate_ready(lifecycle_gate_trace, edge):
        clean_blockers = _unique([item for item in blockers if item not in {"BLOCKED_BY_LIFECYCLE", "STALE_CAPITAL_EVALUATION", "STALE_ORDERBOOK", "STALE_SAME_MARKET_GUARD"}])
        mapped = _state_from_gate_trace(lifecycle_gate_trace)
        clean_blockers.extend(_current_gate_blockers_from_trace(lifecycle_gate_trace, mapped))
        return _state_with_operational(mapped, operational_state, confidence, clean_blockers)

    if paper_simulation_enabled:
        return (
            "ACTIONABLE_SMALL_PAPER",
            "EXECUTION_READY_IF_ENABLED",
            "HIGH",
            [],
            ["Latest lifecycle gate reconciliation is clear; execution remains controlled by Phase 10 paper certification."],
            "READY_FOR_PAPER_CERTIFICATION",
        )
    return (
        "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
        "EXECUTION_DISABLED_PAPER_OFF",
        "HIGH",
        ["PAPER_SIMULATION_OFF"],
        _required(["PAPER_SIMULATION_OFF"]),
        "ENABLE_PAPER_SIMULATION_IN_PHASE_10_ONLY",
    )


def _lifecycle_gate_ready(trace: dict[str, Any], edge: dict[str, Any]) -> bool:
    if trace.get("actionability_class") not in {"ACTIONABLE_SMALL_PAPER", "ACTIONABLE_STANDARD_PAPER", "COMPLETE_HIGH_CONFIDENCE"}:
        return False
    if trace.get("critical_blockers"):
        return False
    if edge and (edge.get("edge_state") != "EDGE_SUPPORTED" or edge.get("source_backed") is not True or edge.get("risk_usable") is not True):
        return False
    risk_capital_trace = trace.get("risk_capital_gate_trace") if isinstance(trace.get("risk_capital_gate_trace"), dict) else {}
    risk_capital_state = str(risk_capital_trace.get("classification") or risk_capital_trace.get("risk_capital_policy_state") or "").upper()
    policy_state = str(risk_capital_trace.get("risk_capital_policy_state") or "").upper()
    return (
        str(trace.get("risk_gate_state") or "").upper() in STRICT_RISK_APPROVED_STATES
        and str(trace.get("capital_gate_state") or "").upper() in STRICT_CAPITAL_STATES
        and (not risk_capital_state or risk_capital_state in STRICT_RISK_CAPITAL_STATES)
        and (not policy_state or policy_state in STRICT_RISK_CAPITAL_STATES)
        and trace.get("orderbook_gate_state") == "FRESH"
        and trace.get("same_market_gate_state") in {"ALLOW", "CAN_AUTHORIZE"}
        and trace.get("exit_gate_state") in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}
        and trace.get("stale_gate_selected") is False
    )


STRICT_ACTIONABLE_STATES = {"ACTIONABLE_SMALL_PAPER", "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"}
STRICT_EVENT_SCOPES = {"CANDIDATE_ACTIONABLE", "CANDIDATE_SCOPED", "CANDIDATE_TARGETED_REFRESH"}
STRICT_LINK_STATES = {"LINKED_TO_CANDIDATE", "HIGH_CONFIDENCE_LINK", "CANDIDATE_LINKED"}
STRICT_RISK_APPROVED_STATES = {"RISK_OK", "RISK_ALLOWED", "RISK_SUPPORT", "RISK_APPROVED"}
STRICT_CAPITAL_STATES = {"CAPITAL_OK", "CAPITAL_SUPPORT", "CAPITAL_EFFICIENCY_OK", "CAPITAL_ALLOWED"}
STRICT_RISK_CAPITAL_STATES = {"PASSED", "CAPITAL_SUPPORT", "CAPITAL_OK", "CAPITAL_ALLOWED", "CAPITAL_EFFICIENCY_OK"}
STRICT_EXIT_READY_STATES = {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}
STRICT_LIFECYCLE_CLASSES = {"ACTIONABLE_SMALL_PAPER", "ACTIONABLE_STANDARD_PAPER", "COMPLETE_HIGH_CONFIDENCE"}


def is_strictly_paper_actionable(item: dict[str, Any]) -> tuple[bool, str | None, list[str], list[str]]:
    """Return strict Phase 10 Paper qualification for a selected actionability row.

    This is intentionally stricter than general monitoring actionability. It is
    the contract used for `ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED`; failing
    rows must stay explanatory/no-trade truth and must not become Paper inputs.
    """

    missing_identity = [field for field in ("candidate_id", "market_id", "side", "token_id") if not item.get(field)]
    if missing_identity:
        return False, "NOT_ACTIONABLE_INCOMPLETE_TRACE", ["INCOMPLETE_CANDIDATE_IDENTITY"], [f"Missing selected row fields: {', '.join(missing_identity)}."]

    scope = str(item.get("candidate_event_scope") or item.get("candidate_event_actionability_scope") or "").upper()
    if scope not in STRICT_EVENT_SCOPES:
        return False, "NOT_ACTIONABLE_EVENT_SCOPE", ["NOT_ACTIONABLE_EVENT_SCOPE"], ["Candidate event scope must be candidate-actionable."]

    link_state = str(item.get("candidate_event_link_state") or "").upper()
    if link_state == "TOKEN_SIDE_MISMATCH":
        return False, "NOT_ACTIONABLE_TOKEN_SIDE_MISMATCH", ["TOKEN_SIDE_MISMATCH"], ["Candidate event link must match selected token and side."]
    if link_state not in STRICT_LINK_STATES:
        return False, "NOT_ACTIONABLE_EVENT_SCOPE", ["NOT_ACTIONABLE_EVENT_SCOPE"], ["Candidate event must be linked to the selected candidate."]

    if item.get("edge_state") != "EDGE_SUPPORTED" or item.get("source_backed") is not True or item.get("risk_usable") is not True:
        return False, "NOT_ACTIONABLE_INCOMPLETE_TRACE", ["EDGE_NOT_STRICTLY_SUPPORTED"], ["Edge must be EDGE_SUPPORTED, source-backed, and risk-usable."]

    risk_state = str(item.get("risk_gate_state") or "").upper()
    if risk_state in {"RISK_REVIEW", "RISK_REVIEW_LINEAGE_PARTIAL", "RISK_WATCH"}:
        return False, "NOT_ACTIONABLE_RISK_REVIEW", ["RISK_REVIEW"], ["Risk must be approved, not review/watch/partial."]
    if risk_state not in STRICT_RISK_APPROVED_STATES:
        return False, "NOT_ACTIONABLE_RISK_BLOCKED", ["RISK_NOT_APPROVED"], ["Risk gate must be RISK_OK/RISK_ALLOWED/RISK_SUPPORT."]

    thesis = item.get("joined_trade_thesis") if isinstance(item.get("joined_trade_thesis"), dict) else {}
    if thesis and (
        str(thesis.get("candidate_id") or "") != str(item.get("candidate_id"))
        or str(thesis.get("side") or "") != str(item.get("side"))
        or str(thesis.get("token_id") or "") != str(item.get("token_id"))
        or str(thesis.get("source_refresh_cycle_id") or "") != str(item.get("source_refresh_cycle_id"))
    ):
        return False, "NOT_ACTIONABLE_MISSING_TRADE_THESIS_LINK", ["MISSING_TRADE_THESIS_LINK"], ["Trade thesis must match candidate, side, token, and source refresh cycle."]
    if not item.get("thesis_id") or not item.get("trade_thesis_type") or str(thesis.get("status") or "").upper() != "THESIS_SUPPORTED":
        return False, "NOT_ACTIONABLE_MISSING_TRADE_THESIS", ["MISSING_TRADE_THESIS"], ["Supported trade thesis must be present on the selected row."]

    if not item.get("exit_intent") or str(item.get("exit_intent")).upper() == "UNKNOWN_EXIT":
        return False, "NOT_ACTIONABLE_MISSING_EXIT_INTENT", ["MISSING_EXIT_INTENT"], ["Trade thesis must include a valid exit intent."]

    if item.get("expected_hold_time_hours") in {None, "", 0, "0"} or not item.get("hold_time_source"):
        return False, "NOT_ACTIONABLE_MISSING_DYNAMIC_HOLD_TIME", ["MISSING_DYNAMIC_HOLD_TIME"], ["Dynamic hold-time trace must be present."]

    risk_capital = item.get("risk_capital_gate_trace") if isinstance(item.get("risk_capital_gate_trace"), dict) else {}
    capital_state = str(item.get("capital_gate_state") or "").upper()
    risk_capital_state = str(risk_capital.get("classification") or item.get("risk_capital_policy_state") or "").upper()
    policy_state = str(item.get("risk_capital_policy_state") or "").upper()
    if capital_state not in STRICT_CAPITAL_STATES or risk_capital_state not in STRICT_RISK_CAPITAL_STATES or (policy_state and policy_state not in STRICT_RISK_CAPITAL_STATES):
        return False, "NOT_ACTIONABLE_CAPITAL_BLOCKED", ["CAPITAL_NOT_STRICTLY_APPROVED"], ["Capital and Risk-Capital policy must be approved/support, not watch or blocked."]

    if not risk_capital:
        return False, "NOT_ACTIONABLE_INCOMPLETE_TRACE", ["CAPITAL_EFFICIENCY_TRACE_MISSING"], ["Capital efficiency trace must be present."]

    exit_state = str(item.get("exit_gate_state") or item.get("exit_readiness_state") or "").upper()
    if exit_state not in STRICT_EXIT_READY_STATES:
        return False, "NOT_ACTIONABLE_EXIT_NOT_READY", ["EXIT_NOT_READY"], ["Exit readiness must be EXIT_READY."]

    trace = item.get("lifecycle_gate_trace") if isinstance(item.get("lifecycle_gate_trace"), dict) else {}
    if trace.get("actionability_class") not in STRICT_LIFECYCLE_CLASSES or trace.get("allow_paper_intent") is not True or trace.get("critical_blockers"):
        return False, "NOT_ACTIONABLE_LIFECYCLE_NOT_ALLOWED", ["LIFECYCLE_NOT_ALLOWED"], ["Lifecycle must allow Paper intent with no critical blockers."]

    if item.get("stale_gate_selected") is True or item.get("stale_sources_blocking"):
        return False, "NOT_ACTIONABLE_STALE_EVIDENCE", ["STALE_EVIDENCE"], ["No stale evidence may block the selected Paper candidate."]

    if "BLOCKED_BY_DUPLICATE" in set(item.get("blockers") or []) or "BLOCKED_BY_OPEN_POSITION" in set(item.get("blockers") or []):
        return False, "NOT_ACTIONABLE_DUPLICATE_OR_OPEN_POSITION_CONFLICT", ["DUPLICATE_OR_OPEN_POSITION_CONFLICT"], ["Duplicate and open-position guards must be clear."]

    return True, None, [], []


def _reconcile_strict_actionability(item: dict[str, Any], *, paper_simulation_enabled: bool) -> dict[str, Any]:
    ok, state, blockers, required = is_strictly_paper_actionable(item)
    item["strict_paper_qualification"] = {
        "qualified": ok,
        "state": "STRICTLY_PAPER_ACTIONABLE" if ok else state,
        "blockers": blockers,
        "required_to_pass": required,
    }
    if ok:
        return item
    should_expose_strict_state = (
        item.get("candidate_paper_actionability_state") in STRICT_ACTIONABLE_STATES
        or item.get("candidate_paper_actionability_state") == "BLOCKED_BY_LIFECYCLE"
    )
    if not should_expose_strict_state:
        return item
    demoted_state = state or "NOT_ACTIONABLE_INCOMPLETE_TRACE"
    merged_blockers = _unique([*(item.get("blockers") or []), *blockers])
    item["candidate_paper_actionability_state"] = demoted_state
    item["paper_actionability_state"] = demoted_state
    item["operational_paper_execution_state"] = "EXECUTION_DISABLED_STRICT_QUALIFICATION"
    item["actionability_confidence"] = "HIGH"
    item["blockers"] = merged_blockers
    item["unified_blockers"] = unified_blockers(
        merged_blockers,
        source="paper_actionability",
        candidate_id=item.get("candidate_id"),
        event_id=item.get("event_id"),
        correlation_id=item.get("correlation_id"),
        market_id=item.get("market_id"),
        side=item.get("side"),
        token_id=item.get("token_id"),
    )
    item["required_to_pass"] = required or _required(merged_blockers)
    item["next_possible_state"] = "FIX_STRICT_PAPER_QUALIFICATION"
    item["would_require_paper_simulation_on"] = False
    item["operator_summary"] = _summary(demoted_state, item["operational_paper_execution_state"], merged_blockers)
    item["propagation_breakpoint"] = item.get("propagation_breakpoint") or demoted_state
    return item


def _state_from_current_lifecycle_blockers(critical: list[str]) -> str:
    joined = set(critical)
    if any(item.startswith("RISK_") for item in joined):
        return "BLOCKED_BY_RISK"
    if any(item.startswith("EXIT_") or item == "STALE_EXIT_PLAN" for item in joined):
        return "BLOCKED_BY_EXIT"
    if any(item.startswith("CAPITAL_") or item == "STALE_CAPITAL_EVALUATION" for item in joined):
        return "BLOCKED_BY_CAPITAL"
    if any(item in {"STALE_ORDERBOOK", "MISSING_FRESH_ORDERBOOK", "TRUSTED_ORDERBOOK_MISSING"} for item in joined):
        return "WAITING_FOR_PRICE_REFRESH"
    return "BLOCKED_BY_LIFECYCLE"


def _state_from_gate_trace(trace: dict[str, Any]) -> str:
    risk_state = str(trace.get("risk_gate_state") or "").upper()
    if risk_state in {"RISK_REVIEW", "RISK_REVIEW_LINEAGE_PARTIAL", "RISK_WATCH"}:
        return "BLOCKED_BY_RISK"
    if risk_state not in STRICT_RISK_APPROVED_STATES:
        return "BLOCKED_BY_RISK"
    capital_state = str(trace.get("capital_gate_state") or "").upper()
    risk_capital_trace = trace.get("risk_capital_gate_trace") if isinstance(trace.get("risk_capital_gate_trace"), dict) else {}
    risk_capital_state = str(risk_capital_trace.get("classification") or risk_capital_trace.get("risk_capital_policy_state") or "").upper()
    policy_state = str(risk_capital_trace.get("risk_capital_policy_state") or "").upper()
    if capital_state not in STRICT_CAPITAL_STATES:
        return "BLOCKED_BY_CAPITAL"
    if risk_capital_state and risk_capital_state not in STRICT_RISK_CAPITAL_STATES:
        return "BLOCKED_BY_CAPITAL"
    if policy_state and policy_state not in STRICT_RISK_CAPITAL_STATES:
        return "BLOCKED_BY_CAPITAL"
    if trace.get("orderbook_gate_state") != "FRESH":
        return "WAITING_FOR_PRICE_REFRESH"
    if trace.get("same_market_gate_state") not in {"ALLOW", "CAN_AUTHORIZE"}:
        return "BLOCKED_BY_LIFECYCLE"
    if trace.get("exit_gate_state") not in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}:
        return "BLOCKED_BY_EXIT"
    return "BLOCKED_BY_LIFECYCLE"


def _current_gate_blocker_from_state(state: str) -> str:
    return {
        "BLOCKED_BY_RISK": "BLOCKED_BY_RISK_CURRENT",
        "BLOCKED_BY_CAPITAL": "BLOCKED_BY_CAPITAL_CURRENT",
        "WAITING_FOR_PRICE_REFRESH": "BLOCKED_BY_ORDERBOOK_CURRENT",
        "BLOCKED_BY_EXIT": "BLOCKED_BY_EXIT_CURRENT",
        "BLOCKED_BY_LIFECYCLE": "BLOCKED_BY_LIFECYCLE_CURRENT",
    }.get(state, "BLOCKED_BY_LIFECYCLE_CURRENT")


def _current_gate_blockers_from_trace(trace: dict[str, Any], mapped_state: str) -> list[str]:
    blockers: list[str] = []
    risk_state = str(trace.get("risk_gate_state") or "").upper()
    if risk_state in {"RISK_REVIEW", "RISK_REVIEW_LINEAGE_PARTIAL", "RISK_WATCH"}:
        blockers.append("BLOCKED_BY_RISK_REVIEW")
    elif risk_state and risk_state not in STRICT_RISK_APPROVED_STATES:
        blockers.append("BLOCKED_BY_RISK_CURRENT")

    risk_capital_trace = trace.get("risk_capital_gate_trace") if isinstance(trace.get("risk_capital_gate_trace"), dict) else {}
    capital_state = str(trace.get("capital_gate_state") or "").upper()
    risk_capital_state = str(risk_capital_trace.get("classification") or risk_capital_trace.get("risk_capital_policy_state") or "").upper()
    policy_state = str(risk_capital_trace.get("risk_capital_policy_state") or "").upper()
    if capital_state == "CAPITAL_WATCH" or risk_capital_state == "CAPITAL_WATCH" or policy_state == "CAPITAL_WATCH":
        blockers.append("BLOCKED_BY_CAPITAL_WATCH")
    elif capital_state and capital_state not in STRICT_CAPITAL_STATES:
        blockers.append("BLOCKED_BY_CAPITAL_CURRENT")
    elif risk_capital_state and risk_capital_state not in STRICT_RISK_CAPITAL_STATES:
        blockers.append("BLOCKED_BY_CAPITAL_CURRENT")
    elif policy_state and policy_state not in STRICT_RISK_CAPITAL_STATES:
        blockers.append("BLOCKED_BY_CAPITAL_CURRENT")

    if trace.get("orderbook_gate_state") != "FRESH":
        blockers.append("BLOCKED_BY_ORDERBOOK_CURRENT")
    if trace.get("same_market_gate_state") not in {"ALLOW", "CAN_AUTHORIZE"}:
        blockers.append("BLOCKED_BY_SAME_MARKET_CURRENT")
    if trace.get("exit_gate_state") not in {"EXIT_READY", "READY", "ALLOW", "SUPPORT"}:
        blockers.append("BLOCKED_BY_EXIT_CURRENT")

    return _unique(blockers or [_current_gate_blocker_from_state(mapped_state)])


def _append_opinion_blockers(blockers: list[str], opinions: dict[str, Any]) -> None:
    capital = opinions.get("capital") or {}
    lifecycle = opinions.get("lifecycle") or {}
    risk = opinions.get("risk") or {}
    exit_opinion = opinions.get("exit") or {}
    capital_state = str(capital.get("capital_opinion_state") or capital.get("state") or "")
    lifecycle_state = str(lifecycle.get("lifecycle_opinion_state") or lifecycle.get("state") or "")
    if capital_state in {"CAPITAL_BLOCKED"}:
        blockers.append("BLOCKED_BY_CAPITAL")
    elif capital_state in {"CAPITAL_MISSING", "CAPITAL_STALE", "CAPITAL_UNKNOWN", "MISSING", "STALE", "UNKNOWN"}:
        blockers.append("WAITING_FOR_CAPITAL")
    if lifecycle_state in {"LIFECYCLE_DENIED"}:
        blockers.append("BLOCKED_BY_LIFECYCLE")
    elif lifecycle_state in {"LIFECYCLE_PARTIAL", "LIFECYCLE_MISSING", "LIFECYCLE_STALE", "LIFECYCLE_UNKNOWN", "MISSING", "STALE", "UNKNOWN"}:
        blockers.append("WAITING_FOR_LIFECYCLE")
    if _opinion_has_blocker(risk):
        blockers.append("BLOCKED_BY_RISK")
    elif _opinion_missing_or_stale(risk):
        blockers.append("WAITING_FOR_RISK")
    if _opinion_has_blocker(exit_opinion):
        blockers.append("BLOCKED_BY_EXIT")
    elif _opinion_missing_or_stale(exit_opinion):
        blockers.append("WAITING_FOR_EXIT")


def _opinion_has_blocker(opinion: dict[str, Any]) -> bool:
    blockers = [str(item).upper() for item in (opinion.get("blockers") or [])]
    state = str(opinion.get("state") or "").upper()
    return bool(blockers) or state in {"BLOCKED", "FAILED", "CONFLICTING"}


def _opinion_missing_or_stale(opinion: dict[str, Any]) -> bool:
    state = str(opinion.get("state") or "").upper()
    return state in {"MISSING", "STALE", "UNKNOWN"} or not opinion


def _has_specific_hard_block(blockers: list[str]) -> bool:
    return any(code in blockers for code in ("BLOCKED_BY_LIFECYCLE", "BLOCKED_BY_CAPITAL", "BLOCKED_BY_RISK", "BLOCKED_BY_EXIT", "BLOCKED_BY_DUPLICATE", "BLOCKED_BY_OPEN_POSITION"))


def _opinion_summary(opinions: dict[str, Any]) -> dict[str, str]:
    return {
        "liquidity": str((opinions.get("liquidity") or {}).get("state") or "UNKNOWN"),
        "risk": str((opinions.get("risk") or {}).get("state") or "UNKNOWN"),
        "exit": str((opinions.get("exit") or {}).get("state") or "UNKNOWN"),
        "capital": str((opinions.get("capital") or {}).get("capital_opinion_state") or (opinions.get("capital") or {}).get("state") or "UNKNOWN"),
        "lifecycle": str((opinions.get("lifecycle") or {}).get("lifecycle_opinion_state") or (opinions.get("lifecycle") or {}).get("state") or "UNKNOWN"),
    }


def _required(blockers: list[str]) -> list[str]:
    shaped = unified_blockers(blockers, source="paper_actionability")
    return [item for blocker in shaped for item in blocker["required_to_pass"]]


def _lifecycle_gate_trace(decision: dict[str, Any], plan: dict[str, Any] | None) -> dict[str, Any]:
    metadata = decision.get("metadata_json") if isinstance(decision.get("metadata_json"), dict) else {}
    plan_metadata = (plan or {}).get("metadata_json") if isinstance((plan or {}).get("metadata_json"), dict) else {}
    risk_trace = metadata.get("risk_source_trace") if isinstance(metadata.get("risk_source_trace"), dict) else {}
    risk_capital_trace = metadata.get("risk_capital_gate_trace") if isinstance(metadata.get("risk_capital_gate_trace"), dict) else {}
    exit_readiness_trace = metadata.get("exit_readiness_trace") if isinstance(metadata.get("exit_readiness_trace"), dict) else {}
    truth_state = metadata.get("truth_state") if isinstance(metadata.get("truth_state"), dict) else {}
    event_capital = truth_state.get("event_native_capital") if isinstance(truth_state.get("event_native_capital"), dict) else {}
    same_market_truth = truth_state.get("same_market_guard") if isinstance(truth_state.get("same_market_guard"), dict) else {}
    freshness = metadata.get("freshness_governance") if isinstance(metadata.get("freshness_governance"), dict) else {}
    checks = [item for item in (freshness.get("checks") or []) if isinstance(item, dict)]
    source_refresh_cycle_id = (
        plan_metadata.get("source_refresh_cycle_id")
        or (plan_metadata.get("propagation_context") or {}).get("source_refresh_cycle_id")
        or metadata.get("source_refresh_cycle_id")
        or (metadata.get("propagation_context") or {}).get("source_refresh_cycle_id")
    )
    same_market_summary = (plan or {}).get("same_market_summary_json") if isinstance((plan or {}).get("same_market_summary_json"), dict) else {}
    source_refs = (plan or {}).get("source_refs_json") if isinstance((plan or {}).get("source_refs_json"), dict) else {}
    critical = [str(item).upper() for item in decision.get("critical_blockers_json") or []]
    stale_selected = any(item.startswith("STALE_") for item in critical)
    current_blocker = _current_lifecycle_blocker(critical)
    return {
        "candidate_id": decision.get("subject_id"),
        "market_id": decision.get("market_id"),
        "condition_id": (plan or {}).get("condition_id") or (plan_metadata.get("propagation_context") or {}).get("condition_id"),
        "side": decision.get("side"),
        "token_id": decision.get("token_id"),
        "source_refresh_cycle_id": source_refresh_cycle_id,
        "mesh_inquiry_session_id": (plan or {}).get("mesh_session_id") or (plan_metadata.get("propagation_context") or {}).get("mesh_inquiry_session_id"),
        "edge_thesis_id": (plan_metadata.get("propagation_context") or {}).get("edge_thesis_id") or risk_trace.get("edge_thesis_id"),
        "risk_evidence_id": risk_trace.get("selected_risk_evidence_evaluation_id") or plan_metadata.get("risk_evidence_id"),
        "capital_evidence_id": event_capital.get("brain_output_id") or _freshness_source_id(checks, "CAPITAL_EVALUATION") or _freshness_source_id(checks, "CAPITAL_EFFICIENCY"),
        "orderbook_snapshot_id": _freshness_source_id(checks, "ORDERBOOK_SNAPSHOT"),
        "same_market_guard_id": same_market_truth.get("source_record_id") or _freshness_source_id(checks, "SAME_MARKET_GUARD") or same_market_summary.get("decision_id"),
        "exit_plan_id": _freshness_source_id(checks, "EXIT_PLAN") or source_refs.get("exit_plan_id"),
        "lifecycle_decision_id": decision.get("decision_id"),
        "actionability_result_id": decision.get("decision_id"),
        "actionability_class": decision.get("actionability_class"),
        "allow_paper_intent": bool(decision.get("allow_paper_intent")),
        "allow_paper_execution": bool(decision.get("allow_paper_execution")),
        "critical_blockers": critical,
        "optional_missing": decision.get("optional_missing_json") or [],
        "context_dependent_missing": decision.get("context_dependent_missing_json") or [],
        "risk_gate_state": risk_trace.get("final_risk_interpretation") or decision.get("risk_status"),
        "risk_capital_gate_trace": risk_capital_trace,
        "exit_gate_trace": exit_readiness_trace,
        "risk_source_freshness": risk_trace.get("selected_risk_source_freshness"),
        "capital_gate_state": event_capital.get("capital_opinion_state") or decision.get("capital_status"),
        "capital_fresh": bool(event_capital.get("fresh")) or _freshness_status(checks, "CAPITAL_EVALUATION") == "FRESH",
        "orderbook_gate_state": _freshness_status(checks, "ORDERBOOK_SNAPSHOT") or "UNKNOWN",
        "same_market_gate_state": same_market_truth.get("decision_permission") or decision.get("same_market_guard_status"),
        "exit_gate_state": decision.get("exit_status"),
        "stale_gate_selected": stale_selected,
        "lifecycle_blocker_current": bool(current_blocker),
        "exact_current_lifecycle_blocker": current_blocker,
        "created_at": decision.get("created_at").isoformat() if hasattr(decision.get("created_at"), "isoformat") else decision.get("created_at"),
        "reason": decision.get("reason"),
    }


def _freshness_source_id(checks: list[dict[str, Any]], source_type: str) -> str | None:
    for check in checks:
        if str(check.get("source_type") or "").upper() == source_type:
            return check.get("source_id")
    return None


def _freshness_status(checks: list[dict[str, Any]], source_type: str) -> str | None:
    for check in checks:
        if str(check.get("source_type") or "").upper() == source_type:
            return str(check.get("freshness_status") or "").upper() or None
    return None


def _current_lifecycle_blocker(critical: list[str]) -> str | None:
    if not critical:
        return None
    for blocker in critical:
        if blocker.startswith("STALE_"):
            return blocker
    return critical[0]


def _decision_cycle_consistent(edge: dict[str, Any], lifecycle_gate_trace: dict[str, Any] | None = None) -> bool:
    context = edge.get("propagation_context") if isinstance(edge.get("propagation_context"), dict) else {}
    edge_ok = bool(edge.get("source_refresh_cycle_id") and context.get("source_refresh_cycle_id") == edge.get("source_refresh_cycle_id") and edge.get("risk_evidence_id"))
    if not edge_ok:
        return False
    trace = lifecycle_gate_trace or {}
    if not trace:
        return edge_ok
    return bool(
        trace.get("source_refresh_cycle_id") == edge.get("source_refresh_cycle_id")
        and trace.get("risk_evidence_id") == edge.get("risk_evidence_id")
        and trace.get("lifecycle_decision_id")
    )


def _source_refresh_latency_seconds(edge: dict[str, Any]) -> int | None:
    context = edge.get("propagation_context") if isinstance(edge.get("propagation_context"), dict) else {}
    value = context.get("source_refresh_completed_at")
    if not value:
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


def _propagation_breakpoint(edge: dict[str, Any], state: str, lifecycle_gate_trace: dict[str, Any] | None = None) -> str | None:
    if not edge:
        return "EDGE_THESIS_MISSING"
    if not edge.get("source_refresh_cycle_id"):
        return "SOURCE_REFRESH_CONTEXT_MISSING"
    if not edge.get("risk_evidence_id"):
        return "RISK_EVIDENCE_CONTEXT_MISSING"
    trace = lifecycle_gate_trace or {}
    if state in {"BLOCKED_BY_LIFECYCLE", "ACTIONABLE_SMALL_PAPER", "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"} and not trace.get("lifecycle_decision_id"):
        return "LIFECYCLE_GATE_TRACE_MISSING"
    if trace and trace.get("stale_gate_selected") and state in {"BLOCKED_BY_LIFECYCLE", "BLOCKED_BY_RISK", "BLOCKED_BY_CAPITAL", "BLOCKED_BY_EXIT", "WAITING_FOR_PRICE_REFRESH"}:
        return "LIFECYCLE_STALE_GATE_SELECTED"
    if state in {"BLOCKED_BY_RISK", "BLOCKED_BY_LIFECYCLE"} and edge.get("edge_state") == "EDGE_STALE" and not edge.get("stale_sources_blocking"):
        return "EDGE_STALE_WITHOUT_BLOCKING_STALE_SOURCE"
    return None


def _top_blockers(items: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in items:
        out.extend(item.get("blockers") or [])
    return _unique(out)


def _top_unified_blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        for blocker in item.get("unified_blockers") or []:
            seen.setdefault(blocker["blocker_code"], blocker)
    return list(seen.values())


def _summary(state: str, operational_state: str, blockers: list[str]) -> str:
    if state in {"ACTIONABLE_SMALL_PAPER", "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"}:
        return f"Candidate has candidate-scoped all-five mesh evidence and maps to {state}; operational state is {operational_state}."
    return f"Candidate is not paper-actionable: {', '.join(blockers) if blockers else state}."


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    return bool(row)


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    status = ControlCenterStatus(payload.get("status") if payload.get("status") in {item.value for item in ControlCenterStatus} else "PARTIAL")
    envelope = truth_envelope(
        status=status,
        source="paper actionability contract",
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
