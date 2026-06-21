from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Callable

from app.db.connection import DatabaseConnectionFactory
from app.services.exit_foundation import ExitFoundationService
from app.runtime.health_truth import HealthTruthService
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService
from app.services.dry_run_provenance import DryRunProvenanceService
from app.services.impact_graph import ImpactGraphService
from app.services.link_coverage import LinkCoverageService
from app.services.lineage_coverage import LineageCoverageService
from app.services.mesh_blockers import MeshBlockersService
from app.services.mesh_dry_run import MeshDryRunService
from app.services.neuron_registry import NeuronRegistryService
from app.services.orderbook_snapshots import OrderbookSnapshotService
from app.services.neuron_signals import NeuronSignalService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.paper_intents import PaperIntentGateService
from app.services.producer_health import ProducerHealthService
from app.services.query.operator_dashboard_query_service import OperatorDashboardQueryService
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
from app.services.runtime_coordinator import RuntimeCoordinatorDecisionService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService
from app.services.risk_core import RiskCoreService
from app.services.signal_market_binding import SignalMarketBindingRecoveryService
from app.services.signal_processing import SignalProcessingService
from app.services.signal_quality import SignalQualityService
from app.services.signal_lineage import SignalLineageService
from app.services.thesis_profiles import ThesisProfileService


class MeshDashboardService:
    """Unified read-only truth surface for Neural Mesh operator awareness."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._operator = OperatorDashboardQueryService(connection_factory=self._factory)

    def get_mesh_dashboard(self, *, limit: int = 20) -> dict[str, Any]:
        updated_at = datetime.now(UTC).isoformat()
        errors: list[str] = []

        runtime = self._safe_layer("runtime", self._runtime_layer, errors)
        sources = self._safe_layer("sources", self._sources_layer, errors)
        neurons = self._safe_layer("neurons", lambda: NeuronRegistryService(connection_factory=self._factory).get_neuron_mesh_summary(), errors)
        signals = self._safe_layer("signals", lambda: _signal_layer(NeuronSignalService(connection_factory=self._factory).get_signal_summary(limit=limit)), errors)
        lineage = self._safe_layer("lineage", lambda: SignalLineageService(connection_factory=self._factory).get_lineage_summary(limit=limit), errors)
        signal_quality = self._safe_layer("signal_quality", lambda: SignalQualityService(connection_factory=self._factory).get_signal_quality_summary(limit=limit), errors)
        signal_processing = self._safe_layer("signal_processing", lambda: SignalProcessingService(connection_factory=self._factory).get_signal_processing_summary(limit=limit), errors)
        link_coverage = self._safe_layer("link_coverage", lambda: LinkCoverageService(connection_factory=self._factory).get_link_coverage_summary(limit=limit), errors)
        lineage_coverage = self._safe_layer("lineage_coverage", lambda: LineageCoverageService(connection_factory=self._factory).get_lineage_coverage_summary(limit=limit), errors)
        impact_graph = self._safe_layer("impact_graph", lambda: ImpactGraphService(connection_factory=self._factory).get_impact_graph_summary(limit=limit), errors)
        brain_outputs = self._safe_layer("brain_outputs", lambda: BrainOutputService(connection_factory=self._factory).get_brain_output_summary(limit=limit), errors)
        coordinator = self._safe_layer("coordinator", lambda: BrainCoordinatorService(connection_factory=self._factory).get_coordinator_summary(limit=limit), errors)
        thesis = self._safe_layer("thesis_profiles", lambda: ThesisProfileService(connection_factory=self._factory).get_dashboard_summary(limit=limit), errors)
        dry_run = self._safe_layer("dry_run", lambda: MeshDryRunService(connection_factory=self._factory).get_dry_run_summary(limit=limit), errors)
        dry_run_provenance = self._safe_layer("dry_run_provenance", lambda: DryRunProvenanceService(connection_factory=self._factory).get_summary(limit=limit), errors)
        producer_health = self._safe_layer("producer_health", lambda: ProducerHealthService(connection_factory=self._factory).get_producer_health_summary(limit=limit), errors)
        runtime_producer_evidence = self._safe_layer(
            "runtime_producer_evidence",
            lambda: RuntimeProducerEvidenceService(connection_factory=self._factory).get_dashboard_summary(limit=limit),
            errors,
        )
        runtime_brain = self._safe_layer(
            "runtime_brain",
            lambda: RuntimeBrainAdapterService(connection_factory=self._factory).get_dashboard_summary(limit=limit),
            errors,
        )
        runtime_coordinator = self._safe_layer(
            "runtime_coordinator",
            lambda: RuntimeCoordinatorDecisionService(connection_factory=self._factory).get_dashboard_summary(limit=limit),
            errors,
        )
        orderbook = self._safe_layer("orderbook", lambda: OrderbookSnapshotService(connection_factory=self._factory).get_dashboard_summary(limit=limit), errors)
        market_binding = self._safe_layer("market_binding", lambda: SignalMarketBindingRecoveryService(connection_factory=self._factory).get_dashboard_summary(limit=limit), errors)
        risk_core = self._safe_layer("risk_core", lambda: RiskCoreService(connection_factory=self._factory).get_dashboard_summary(limit=limit), errors)
        exit_foundation = self._safe_layer("exit_foundation", lambda: ExitFoundationService(connection_factory=self._factory).get_dashboard_summary(limit=limit), errors)
        paper_eligibility = self._safe_layer("paper_eligibility", lambda: PaperEligibilityService(connection_factory=self._factory).get_dashboard_summary(limit=limit), errors)
        paper_intents = self._safe_layer("paper_intents", lambda: PaperIntentGateService(connection_factory=self._factory).get_dashboard_summary(limit=limit), errors)
        no_trade_ledger = self._safe_layer("no_trade", lambda: PaperIntentGateService(connection_factory=self._factory).get_no_trade_dashboard_summary(limit=limit), errors)
        mesh_blockers = self._safe_layer("mesh_blockers", lambda: MeshBlockersService(connection_factory=self._factory).get_mesh_blockers(limit=limit), errors)
        opportunities = self._safe_layer("opportunities", lambda: self._operator_layer("opportunities", self._operator._opportunities_overview()), errors)
        no_trade_operator = self._safe_layer("no_trade_operator", lambda: self._operator_layer("no_trade", self._operator._no_trade_overview()), errors)
        exit_layer = self._safe_layer("exit", lambda: self._operator_layer("exit", self._operator._exit_overview()), errors)
        ai = self._safe_layer("ai", lambda: self._operator_layer("ai", self._operator._ai_brain_overview()), errors)
        risk = self._safe_layer("risk", lambda: self._operator_layer("risk", self._operator._risk_overview()), errors)

        flow = self._flow(
            limit=limit,
            signals=signals,
            lineage=lineage,
            signal_quality=signal_quality,
            signal_processing=signal_processing,
            link_coverage=link_coverage,
            lineage_coverage=lineage_coverage,
            impact_graph=impact_graph,
            brain_outputs=brain_outputs,
            coordinator=coordinator,
            thesis=thesis,
            dry_run=dry_run,
            dry_run_provenance=dry_run_provenance,
            producer_health=producer_health,
            runtime_producer_evidence=runtime_producer_evidence,
            runtime_brain=runtime_brain,
            runtime_coordinator=runtime_coordinator,
            orderbook=orderbook,
            market_binding=market_binding,
            risk_core=risk_core,
            exit_foundation=exit_foundation,
            paper_eligibility=paper_eligibility,
            paper_intents=paper_intents,
            no_trade=no_trade_ledger,
            mesh_blockers=mesh_blockers,
        )
        alerts = self._alerts(
            sources=sources,
            neurons=neurons,
            signals=signals,
            lineage=lineage,
            signal_quality=signal_quality,
            signal_processing=signal_processing,
            link_coverage=link_coverage,
            lineage_coverage=lineage_coverage,
            impact_graph=impact_graph,
            brain_outputs=brain_outputs,
            coordinator=coordinator,
            thesis=thesis,
            dry_run=dry_run,
            dry_run_provenance=dry_run_provenance,
            producer_health=producer_health,
            runtime_producer_evidence=runtime_producer_evidence,
            runtime_brain=runtime_brain,
            runtime_coordinator=runtime_coordinator,
            orderbook=orderbook,
            market_binding=market_binding,
            risk_core=risk_core,
            exit_foundation=exit_foundation,
            paper_eligibility=paper_eligibility,
            paper_intents=paper_intents,
            no_trade=no_trade_ledger,
            mesh_blockers=mesh_blockers,
            opportunities=opportunities,
            exit_layer=exit_layer,
            ai=ai,
            runtime=runtime,
            errors=errors,
        )
        readiness = self._readiness(
            runtime=runtime,
            sources=sources,
            neurons=neurons,
            signals=signals,
            lineage=lineage,
            signal_quality=signal_quality,
            signal_processing=signal_processing,
            link_coverage=link_coverage,
            lineage_coverage=lineage_coverage,
            impact_graph=impact_graph,
            brain_outputs=brain_outputs,
            coordinator=coordinator,
            thesis=thesis,
            dry_run=dry_run,
            dry_run_provenance=dry_run_provenance,
            errors=errors,
        )
        readiness["paper_ready"] = False
        readiness["overall_status"] = mesh_blockers.get("overall_status", readiness.get("overall_status"))
        readiness["blocker_counts"] = mesh_blockers.get("counts", {})
        readiness["top_blockers"] = mesh_blockers.get("blockers", [])[:10]
        readiness["producer_health_summary"] = {
            "overall_status": producer_health.get("overall_status"),
            "runtime_active_producers": producer_health.get("runtime_active_producers", 0),
            "dry_run_only_producers": producer_health.get("dry_run_only_producers", 0),
            "silent_expected_neurons": producer_health.get("silent_expected_neurons", []),
            "missing_neurons": producer_health.get("missing_neurons", []),
            "degraded_neurons": producer_health.get("degraded_neurons", []),
        }
        readiness["runtime_producer_evidence_summary"] = {
            "status": runtime_producer_evidence.get("status"),
            "signals_created": runtime_producer_evidence.get("signals_created", 0),
            "quality_updated": runtime_producer_evidence.get("quality_updated", 0),
            "processing_updated": runtime_producer_evidence.get("processing_updated", 0),
            "lineage_updated": runtime_producer_evidence.get("lineage_updated", 0),
            "link_coverage_updated": runtime_producer_evidence.get("link_coverage_updated", 0),
            "provenance_updated": runtime_producer_evidence.get("provenance_updated", 0),
            "paper_ready": False,
        }
        readiness["runtime_brain_summary"] = {
            "status": runtime_brain.get("status"),
            "runtime_brain_outputs": runtime_brain.get("runtime_brain_outputs", 0),
            "dry_run_brain_outputs": runtime_brain.get("dry_run_brain_outputs", 0),
            "eligible_runtime_signals": runtime_brain.get("eligible_runtime_signals", 0),
            "no_trade_candidates": runtime_brain.get("no_trade_candidates", 0),
            "paper_ready": False,
        }
        readiness["runtime_coordinator_summary"] = {
            "status": runtime_coordinator.get("status"),
            "runtime_coordinator_decisions": runtime_coordinator.get("runtime_coordinator_decisions", 0),
            "dry_run_coordinator_decisions": runtime_coordinator.get("dry_run_coordinator_decisions", 0),
            "eligible_runtime_brain_outputs": runtime_coordinator.get("eligible_runtime_brain_outputs", 0),
            "no_trade_decisions": runtime_coordinator.get("no_trade_decisions", 0),
            "paper_ready": False,
        }
        readiness["orderbook_summary"] = {
            "status": orderbook.get("status"),
            "total_snapshots": orderbook.get("total_snapshots", 0),
            "fresh_snapshots": orderbook.get("fresh_snapshots", 0),
            "stale_snapshots": orderbook.get("stale_snapshots", 0),
            "orderbook_coverage_ratio": orderbook.get("orderbook_coverage_ratio", 0.0),
            "avg_spread": orderbook.get("avg_spread", 0.0),
            "avg_liquidity_score": orderbook.get("avg_liquidity_score", 0.0),
            "paper_ready": False,
        }
        readiness["market_binding_summary"] = {
            "status": market_binding.get("status"),
            "signal_market_links": market_binding.get("signal_market_links", 0),
            "linked_runtime_signals": market_binding.get("linked_runtime_signals", 0),
            "unlinked_runtime_signals": market_binding.get("unlinked_runtime_signals", 0),
            "safe_links_created_last_run": market_binding.get("safe_links_created_last_run", 0),
            "suggestions_created_last_run": market_binding.get("suggestions_created_last_run", 0),
            "link_coverage_ratio": market_binding.get("link_coverage_ratio", 0.0),
            "paper_ready": False,
        }
        readiness["thesis_summary"] = {
            "status": thesis.get("status"),
            "total_thesis_profiles": thesis.get("total_thesis_profiles", 0),
            "complete_thesis_profiles": thesis.get("complete_thesis_profiles", 0),
            "incomplete_thesis_profiles": thesis.get("incomplete_thesis_profiles", 0),
            "blocked_thesis_profiles": thesis.get("blocked_thesis_profiles", 0),
            "weak_thesis_profiles": thesis.get("weak_thesis_profiles", 0),
            "paper_candidate_allowed_count": thesis.get("paper_candidate_allowed_count", 0),
            "paper_ready": False,
        }
        readiness["risk_summary"] = {
            "status": risk_core.get("status"),
            "total_risk_decisions": risk_core.get("total_risk_decisions", 0),
            "approved_count": risk_core.get("approved_count", 0),
            "rejected_count": risk_core.get("rejected_count", 0),
            "blocked_count": risk_core.get("blocked_count", 0),
            "warning_count": risk_core.get("warning_count", 0),
            "avg_risk_score": risk_core.get("avg_risk_score", 0.0),
            "paper_candidate_allowed_count": risk_core.get("paper_candidate_allowed_count", 0),
            "risk_approved_count": risk_core.get("risk_approved_count", 0),
            "execution_allowed_count": risk_core.get("execution_allowed_count", 0),
            "paper_ready": False,
        }
        readiness["exit_summary"] = {
            "status": exit_foundation.get("status"),
            "total_exit_plans": exit_foundation.get("total_exit_plans", 0),
            "complete_exit_plans": exit_foundation.get("complete_exit_plans", 0),
            "incomplete_exit_plans": exit_foundation.get("incomplete_exit_plans", 0),
            "blocked_exit_plans": exit_foundation.get("blocked_exit_plans", 0),
            "paper_exit_ready_count": exit_foundation.get("paper_exit_ready_count", 0),
            "paper_intent_allowed_count": exit_foundation.get("paper_intent_allowed_count", 0),
            "execution_allowed_count": exit_foundation.get("execution_allowed_count", 0),
            "paper_ready": False,
        }
        readiness["paper_eligibility_summary"] = {
            "status": paper_eligibility.get("status"),
            "total_candidates": paper_eligibility.get("total_candidates", 0),
            "eligible_count": paper_eligibility.get("eligible_count", 0),
            "ineligible_count": paper_eligibility.get("ineligible_count", 0),
            "blocked_count": paper_eligibility.get("blocked_count", 0),
            "incomplete_count": paper_eligibility.get("incomplete_count", 0),
            "paper_intent_allowed_count": paper_eligibility.get("paper_intent_allowed_count", 0),
            "execution_allowed_count": paper_eligibility.get("execution_allowed_count", 0),
            "paper_ready": False,
        }
        readiness["paper_intent_summary"] = {
            "status": paper_intents.get("status"),
            "total_paper_intents": paper_intents.get("total_paper_intents", 0),
            "created_intents": paper_intents.get("created_intents", 0),
            "paper_only_true_count": paper_intents.get("paper_only_true_count", 0),
            "live_true_count": paper_intents.get("live_true_count", 0),
            "execution_allowed_count": paper_intents.get("execution_allowed_count", 0),
            "order_intent_created_count": paper_intents.get("order_intent_created_count", 0),
            "accounted_candidates": paper_intents.get("accounted_candidates", 0),
            "unaccounted_candidates": paper_intents.get("unaccounted_candidates", 0),
            "paper_ready": False,
        }
        readiness["no_trade_summary"] = {
            "status": no_trade_ledger.get("status"),
            "total_no_trade_records": no_trade_ledger.get("total_no_trade_records", 0),
            "blocked_candidates": no_trade_ledger.get("blocked_candidates", 0),
            "unaccounted_candidates": no_trade_ledger.get("unaccounted_candidates", 0),
            "paper_ready": False,
        }
        readiness["blocked_by"] = sorted(set(readiness.get("blocked_by", [])) | set(mesh_blockers.get("blocked_by", [])))
        status = _overall_status(errors, alerts)
        return _json_safe(
            {
                "status": status,
                "mock_data": False,
                "updated_at": updated_at,
                "runtime": runtime,
                "mesh_summary": {
                    "overall_status": status,
                    "active_sources": sources.get("active_sources", 0),
                    "active_neurons": neurons.get("active_neurons", 0),
                    "signals_per_minute": signals.get("signals_per_minute", 0.0),
                    "signals_24h": signals.get("signals_24h", 0),
                    "unlinked_signals": impact_graph.get("unlinked_signals", 0),
                    "signal_quality_avg": signal_quality.get("avg_quality_score", 0.0),
                    "signals_can_feed_brain": signal_quality.get("can_feed_brain", 0),
                    "signals_can_feed_paper": signal_quality.get("can_feed_paper", 0),
                    "signal_processing_total": signal_processing.get("total", 0),
                    "signal_processing_unprocessed": signal_processing.get("unprocessed_count", 0),
                    "signal_processing_brain_eligible": signal_processing.get("brain_eligible_count", 0),
                    "link_coverage_ratio": link_coverage.get("link_coverage_ratio", 0.0),
                    "link_coverage_unlinked": link_coverage.get("unlinked_signals", 0),
                    "lineage_coverage_ratio": lineage_coverage.get("lineage_coverage_ratio", 0.0),
                    "lineage_coverage_unbound": lineage_coverage.get("unbound_signals", 0),
                    "brain_outputs_24h": brain_outputs.get("total_outputs_24h", 0),
                    "coordinator_decisions_24h": coordinator.get("total_decisions_24h", 0),
                    "impact_links_total": impact_graph.get("impact_links_total", 0),
                    "thesis_profiles_total": thesis.get("total_thesis_profiles", 0),
                    "dry_runs_24h": len(dry_run.get("recent_dry_runs", [])),
                    "brain_outputs_runtime": dry_run_provenance.get("brain_outputs_runtime", 0),
                    "brain_outputs_dry_run": dry_run_provenance.get("brain_outputs_dry_run", 0),
                    "coordinator_decisions_runtime": dry_run_provenance.get("coordinator_decisions_runtime", 0),
                    "coordinator_decisions_dry_run": dry_run_provenance.get("coordinator_decisions_dry_run", 0),
                    "runtime_active_producers": producer_health.get("runtime_active_producers", 0),
                    "dry_run_only_producers": producer_health.get("dry_run_only_producers", 0),
                    "runtime_evidence_signals_created": runtime_producer_evidence.get("signals_created", 0),
                    "runtime_evidence_quality_updated": runtime_producer_evidence.get("quality_updated", 0),
                    "runtime_evidence_processing_updated": runtime_producer_evidence.get("processing_updated", 0),
                    "runtime_brain_outputs": runtime_brain.get("runtime_brain_outputs", 0),
                    "runtime_brain_outputs_created_last_run": runtime_brain.get("runtime_brain_outputs_created_last_run", 0),
                    "runtime_brain_eligible_signals": runtime_brain.get("eligible_runtime_signals", 0),
                    "runtime_coordinator_decisions": runtime_coordinator.get("runtime_coordinator_decisions", 0),
                    "runtime_coordinator_decisions_created_last_run": runtime_coordinator.get("runtime_coordinator_decisions_created_last_run", 0),
                    "runtime_coordinator_eligible_brain_outputs": runtime_coordinator.get("eligible_runtime_brain_outputs", 0),
                    "orderbook_total_snapshots": orderbook.get("total_snapshots", 0),
                    "orderbook_fresh_snapshots": orderbook.get("fresh_snapshots", 0),
                    "orderbook_stale_snapshots": orderbook.get("stale_snapshots", 0),
                    "orderbook_coverage_ratio": orderbook.get("orderbook_coverage_ratio", 0.0),
                    "market_binding_links": market_binding.get("signal_market_links", 0),
                    "market_binding_linked_runtime_signals": market_binding.get("linked_runtime_signals", 0),
                    "market_binding_unlinked_runtime_signals": market_binding.get("unlinked_runtime_signals", 0),
                    "risk_core_decisions": risk_core.get("total_risk_decisions", 0),
                    "risk_core_blocked": risk_core.get("blocked_count", 0),
                    "risk_core_approved": risk_core.get("approved_count", 0),
                    "exit_foundation_plans": exit_foundation.get("total_exit_plans", 0),
                    "exit_foundation_blocked": exit_foundation.get("blocked_exit_plans", 0),
                    "exit_foundation_complete": exit_foundation.get("complete_exit_plans", 0),
                    "paper_eligibility_candidates": paper_eligibility.get("total_candidates", 0),
                    "paper_eligibility_eligible": paper_eligibility.get("eligible_count", 0),
                    "paper_eligibility_blocked": paper_eligibility.get("blocked_count", 0),
                    "paper_intents_total": paper_intents.get("total_paper_intents", 0),
                    "no_trade_records_total": no_trade_ledger.get("total_no_trade_records", 0),
                    "unaccounted_candidates": paper_intents.get("unaccounted_candidates", 0),
                    "paper_blockers_active": mesh_blockers.get("counts", {}).get("active_blockers", 0),
                    "execution_allowed_count": coordinator.get("execution_allowed_count", 0),
                },
                "layers": {
                    "sources": sources,
                    "neurons": neurons,
                    "signals": signals,
                    "lineage": lineage,
                    "signal_quality": signal_quality,
                    "signal_processing": signal_processing,
                    "link_coverage": link_coverage,
                    "lineage_coverage": lineage_coverage,
                    "impact_graph": impact_graph,
                    "brain_outputs": brain_outputs,
                    "coordinator": coordinator,
                    "thesis": thesis,
                    "thesis_profiles": thesis,
                    "dry_run": dry_run,
                    "dry_run_provenance": dry_run_provenance,
                    "producer_health": producer_health,
                    "runtime_producer_evidence": runtime_producer_evidence,
                    "runtime_brain": runtime_brain,
                    "runtime_coordinator": runtime_coordinator,
                    "orderbook": orderbook,
                    "market_binding": market_binding,
                    "risk_core": risk_core,
                    "exit_foundation": exit_foundation,
                    "paper_eligibility": paper_eligibility,
                    "paper_intents": paper_intents,
                    "mesh_blockers": mesh_blockers,
                    "opportunities": opportunities,
                    "no_trade": no_trade_ledger,
                    "no_trade_operator": no_trade_operator,
                    "exit": exit_layer,
                    "ai": ai,
                    "risk": risk,
                },
                "flow": flow,
                "alerts": alerts,
                "readiness": readiness,
            }
        )

    def _safe_layer(self, name: str, loader: Callable[[], dict[str, Any]], errors: list[str]) -> dict[str, Any]:
        try:
            payload = loader()
            payload.setdefault("status", _infer_layer_status(payload))
            payload.setdefault("mock_data", False)
            return payload
        except Exception as exc:
            message = f"{name}:{type(exc).__name__}:{exc}"
            errors.append(message)
            return {"status": "ERROR", "mock_data": False, "errors": [message]}

    def _runtime_layer(self) -> dict[str, Any]:
        health = HealthTruthService(connection_factory=self._factory).get_health_truth()
        persisted_mode = health.get("current_mode")
        env_mode = os.getenv("POLYBOT_RUNTIME_MODE")
        live_enabled = _str_bool(os.getenv("LIVE_TRADING_ENABLED"))
        kill_env = _str_bool(os.getenv("LIVE_KILL_SWITCH"))
        return {
            "status": "OK" if health.get("overall_status") in {"HEALTHY", "OK"} else "DEGRADED",
            "current_mode": persisted_mode,
            "runtime_health": health.get("overall_status"),
            "healthy": health.get("overall_status") in {"HEALTHY", "OK"},
            "live_enabled": bool(live_enabled),
            "env_mode": env_mode,
            "persisted_mode": persisted_mode,
            "kill_switch_env": kill_env,
            "kill_switch_persisted": health.get("kill_switch_active"),
            "mode_mismatch": bool(env_mode and persisted_mode and env_mode != persisted_mode),
            "kill_switch_mismatch": kill_env is not None and health.get("kill_switch_active") is not None and kill_env != bool(health.get("kill_switch_active")),
            "permissions": health.get("permissions") or {},
        }

    def _sources_layer(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_sources("DISABLED")
        with self._factory.connect() as conn:
            if not _table_exists(conn, "source_status"):
                return _empty_sources("MISSING")
            rows = [dict(row) for row in conn.execute("SELECT * FROM source_status ORDER BY source_name").fetchall()]
        active = [row for row in rows if row.get("runtime_status") == "ACTIVE"]
        degraded = [row for row in rows if row.get("runtime_status") == "DEGRADED"]
        missing = [row for row in rows if row.get("runtime_status") == "MISSING"]
        errors = [
            {
                "source_name": row.get("source_name"),
                "runtime_status": row.get("runtime_status"),
                "last_error_at": row.get("last_error_at"),
                "notes": row.get("notes"),
            }
            for row in rows
            if row.get("runtime_status") in {"DEGRADED", "MISSING"}
        ]
        return {
            "status": "DEGRADED" if degraded or missing else "OK" if active else "EMPTY",
            "mock_data": False,
            "active_sources": len(active),
            "degraded_sources": len(degraded),
            "missing_sources": len(missing),
            "disabled_sources": len([row for row in rows if row.get("runtime_status") == "DISABLED"]),
            "source_errors": _json_safe(errors),
            "latest_source_update": _max_time(row.get("updated_at") for row in rows),
            "sources": _json_safe(rows),
        }

    def _operator_layer(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": _operator_status(name, payload, self._factory),
            "mock_data": False,
            **payload,
        }

    def _flow(
        self,
        *,
        limit: int,
        signals: dict[str, Any],
        lineage: dict[str, Any],
        signal_quality: dict[str, Any],
        signal_processing: dict[str, Any],
        link_coverage: dict[str, Any],
        lineage_coverage: dict[str, Any],
        impact_graph: dict[str, Any],
        brain_outputs: dict[str, Any],
        coordinator: dict[str, Any],
        thesis: dict[str, Any],
        dry_run: dict[str, Any],
        dry_run_provenance: dict[str, Any],
        producer_health: dict[str, Any],
        runtime_producer_evidence: dict[str, Any],
        runtime_brain: dict[str, Any],
        runtime_coordinator: dict[str, Any],
        orderbook: dict[str, Any],
        market_binding: dict[str, Any],
        risk_core: dict[str, Any],
        exit_foundation: dict[str, Any],
        paper_eligibility: dict[str, Any],
        paper_intents: dict[str, Any],
        no_trade: dict[str, Any],
        mesh_blockers: dict[str, Any],
    ) -> dict[str, Any]:
        unlinked = []
        signals_by_market: list[dict[str, Any]] = []
        if self._factory.enabled:
            try:
                unlinked = ImpactGraphService(connection_factory=self._factory).list_unlinked_signals(limit=limit)
                with self._factory.connect() as conn:
                    if _table_exists(conn, "neuron_signals"):
                        signals_by_market = [
                            dict(row)
                            for row in conn.execute(
                                """
                                SELECT market_id, COUNT(*) AS count, MAX(created_at) AS latest_signal_at
                                FROM neuron_signals
                                WHERE market_id IS NOT NULL
                                  AND created_at >= now() - interval '24 hours'
                                GROUP BY market_id
                                ORDER BY count DESC, latest_signal_at DESC
                                LIMIT %s
                                """,
                                (limit,),
                            ).fetchall()
                        ]
            except Exception:
                unlinked = []
                signals_by_market = []
        return {
            "signals_by_neuron": signals.get("signals_by_neuron", []),
            "signals_by_market": _json_safe(signals_by_market),
            "latest_signals": signals.get("latest_signals", []),
            "signal_quality": {
                "avg_quality_score": signal_quality.get("avg_quality_score", 0.0),
                "can_feed_brain": signal_quality.get("can_feed_brain", 0),
                "can_feed_paper": signal_quality.get("can_feed_paper", 0),
                "low_quality_count": signal_quality.get("low_quality_count", 0),
                "missing_fields_top": signal_quality.get("missing_fields_summary", []),
                "paper_blocking_reasons": signal_quality.get("paper_blocking_reasons", []),
            },
            "signal_processing": {
                "total": signal_processing.get("total", 0),
                "by_state": signal_processing.get("by_state", []),
                "by_gate_status": signal_processing.get("by_gate_status", []),
                "unprocessed_count": signal_processing.get("unprocessed_count", 0),
                "quality_checked_count": signal_processing.get("quality_checked_count", 0),
                "brain_used_count": signal_processing.get("brain_used_count", 0),
                "coordinator_used_count": signal_processing.get("coordinator_used_count", 0),
                "stale_count": signal_processing.get("stale_count", 0),
                "rejected_count": signal_processing.get("rejected_count", 0),
                "error_count": signal_processing.get("error_count", 0),
                "brain_eligible_count": signal_processing.get("brain_eligible_count", 0),
                "paper_eligible_informational_count": signal_processing.get("paper_eligible_informational_count", 0),
                "top_gate_blockers": signal_processing.get("top_gate_blockers", []),
            },
            "link_coverage": {
                "total_signals": link_coverage.get("total_signals", 0),
                "linked_signals": link_coverage.get("linked_signals", 0),
                "unlinked_signals": link_coverage.get("unlinked_signals", 0),
                "link_coverage_ratio": link_coverage.get("link_coverage_ratio", 0.0),
                "linkable_signals": link_coverage.get("linkable_signals", 0),
                "non_linkable_signals": link_coverage.get("non_linkable_signals", 0),
                "needs_more_evidence": link_coverage.get("needs_more_evidence", 0),
                "stale_unlinked": link_coverage.get("stale_unlinked", 0),
                "dry_run_only_unlinked": link_coverage.get("dry_run_only_unlinked", 0),
                "unlinked_by_reason": link_coverage.get("unlinked_by_reason", []),
                "suggested_market_links_count": link_coverage.get("suggested_market_links_count", 0),
                "safe_to_link_count": link_coverage.get("safe_to_link_count", 0),
                "last_analysis_at": link_coverage.get("last_analysis_at"),
            },
            "lineage_coverage": {
                "total_signals": lineage_coverage.get("total_signals", 0),
                "bound_signals": lineage_coverage.get("bound_signals", 0),
                "unbound_signals": lineage_coverage.get("unbound_signals", 0),
                "complete_lineage": lineage_coverage.get("complete_lineage", 0),
                "partial_lineage": lineage_coverage.get("partial_lineage", 0),
                "lineage_coverage_ratio": lineage_coverage.get("lineage_coverage_ratio", 0.0),
                "dry_run_only_signals": lineage_coverage.get("dry_run_only_signals", 0),
                "runtime_verified_signals": lineage_coverage.get("runtime_verified_signals", 0),
                "unbound_by_reason": lineage_coverage.get("unbound_by_reason", []),
                "missing_lineage_fields": lineage_coverage.get("missing_lineage_fields", []),
                "producer_coverage": lineage_coverage.get("producer_coverage", []),
                "source_coverage": lineage_coverage.get("source_coverage", []),
                "raw_payload_coverage": lineage_coverage.get("raw_payload_coverage", {}),
                "correlation_coverage": lineage_coverage.get("correlation_coverage", {}),
                "avg_lineage_trust_score": lineage_coverage.get("avg_lineage_trust_score", 0.0),
                "last_analysis_at": lineage_coverage.get("last_analysis_at"),
            },
            "unlinked_signals": unlinked or lineage.get("latest_unbound_signals", []),
            "latest_brain_outputs": brain_outputs.get("latest_outputs", []),
            "recent_conflicts": coordinator.get("recent_conflicts") or brain_outputs.get("recent_conflicts", []),
            "recent_coordinator_decisions": coordinator.get("recent_decisions", []),
            "latest_impact_links": impact_graph.get("latest_impacts", []),
            "latest_thesis_profiles": thesis.get("latest_thesis_profiles", []),
            "thesis_profiles": {
                "total_thesis_profiles": thesis.get("total_thesis_profiles", 0),
                "complete_thesis_profiles": thesis.get("complete_thesis_profiles", 0),
                "incomplete_thesis_profiles": thesis.get("incomplete_thesis_profiles", 0),
                "blocked_thesis_profiles": thesis.get("blocked_thesis_profiles", 0),
                "weak_thesis_profiles": thesis.get("weak_thesis_profiles", 0),
                "missing_evidence_summary": thesis.get("missing_evidence_summary", []),
                "invalidation_rule_summary": thesis.get("invalidation_rule_summary", []),
                "risk_notes_summary": thesis.get("risk_notes_summary", []),
                "paper_candidate_allowed_count": thesis.get("paper_candidate_allowed_count", 0),
                "paper_ready": False,
            },
            "latest_dry_run": dry_run.get("latest_dry_run"),
            "dry_run_provenance": {
                "brain_outputs_total": dry_run_provenance.get("brain_outputs_total", 0),
                "brain_outputs_runtime": dry_run_provenance.get("brain_outputs_runtime", 0),
                "brain_outputs_dry_run": dry_run_provenance.get("brain_outputs_dry_run", 0),
                "coordinator_decisions_total": dry_run_provenance.get("coordinator_decisions_total", 0),
                "coordinator_decisions_runtime": dry_run_provenance.get("coordinator_decisions_runtime", 0),
                "coordinator_decisions_dry_run": dry_run_provenance.get("coordinator_decisions_dry_run", 0),
                "generated_by_counts": dry_run_provenance.get("generated_by_counts", []),
                "provenance_status_counts": dry_run_provenance.get("provenance_status_counts", []),
                "dry_run_by_id": dry_run_provenance.get("dry_run_by_id", []),
                "producer_name_coverage": dry_run_provenance.get("producer_name_coverage", []),
                "unknown_provenance_count": dry_run_provenance.get("unknown_provenance_count", 0),
                "blocked_from_paper_count": dry_run_provenance.get("blocked_from_paper_count", 0),
                "last_analysis_at": dry_run_provenance.get("last_analysis_at"),
            },
            "mesh_blockers": {
                "paper_ready": mesh_blockers.get("paper_ready", False),
                "overall_status": mesh_blockers.get("overall_status"),
                "blocked_by": mesh_blockers.get("blocked_by", []),
                "blocker_counts": mesh_blockers.get("counts", {}),
                "top_blockers": mesh_blockers.get("blockers", [])[:10],
                "info": mesh_blockers.get("info", []),
            },
            "producer_health": {
                "overall_status": producer_health.get("overall_status"),
                "total_producers": producer_health.get("total_producers", 0),
                "registered_producers": producer_health.get("registered_producers", 0),
                "observed_producers": producer_health.get("observed_producers", 0),
                "runtime_active_producers": producer_health.get("runtime_active_producers", 0),
                "dry_run_only_producers": producer_health.get("dry_run_only_producers", 0),
                "silent_expected_neurons": producer_health.get("silent_expected_neurons", []),
                "missing_neurons": producer_health.get("missing_neurons", []),
                "degraded_neurons": producer_health.get("degraded_neurons", []),
                "neuron_runtime_truth": producer_health.get("neuron_runtime_truth", {}),
            },
            "runtime_producer_evidence": {
                "status": runtime_producer_evidence.get("status"),
                "latest_run": runtime_producer_evidence.get("latest_run"),
                "runtime_producers_active_after": runtime_producer_evidence.get("runtime_producers_active_after", 0),
                "dry_run_only_producers_after": runtime_producer_evidence.get("dry_run_only_producers_after", 0),
                "signals_created": runtime_producer_evidence.get("signals_created", 0),
                "signals_updated": runtime_producer_evidence.get("signals_updated", 0),
                "quality_updated": runtime_producer_evidence.get("quality_updated", 0),
                "processing_updated": runtime_producer_evidence.get("processing_updated", 0),
                "lineage_updated": runtime_producer_evidence.get("lineage_updated", 0),
                "link_coverage_updated": runtime_producer_evidence.get("link_coverage_updated", 0),
                "provenance_updated": runtime_producer_evidence.get("provenance_updated", 0),
                "producer_health_updated": runtime_producer_evidence.get("producer_health_updated", False),
                "mesh_blockers_updated": runtime_producer_evidence.get("mesh_blockers_updated", False),
                "remaining_blockers": runtime_producer_evidence.get("remaining_blockers", []),
                "paper_ready": False,
            },
            "runtime_brain": {
                "status": runtime_brain.get("status"),
                "latest_run": runtime_brain.get("latest_run"),
                "runtime_brain_outputs": runtime_brain.get("runtime_brain_outputs", 0),
                "dry_run_brain_outputs": runtime_brain.get("dry_run_brain_outputs", 0),
                "runtime_brain_outputs_created_last_run": runtime_brain.get("runtime_brain_outputs_created_last_run", 0),
                "eligible_runtime_signals": runtime_brain.get("eligible_runtime_signals", 0),
                "weak_runtime_signals": runtime_brain.get("weak_runtime_signals", 0),
                "no_trade_candidates": runtime_brain.get("no_trade_candidates", 0),
                "input_signal_count": runtime_brain.get("input_signal_count", 0),
                "remaining_blockers": runtime_brain.get("remaining_blockers", []),
                "paper_ready": False,
            },
            "runtime_coordinator": {
                "status": runtime_coordinator.get("status"),
                "latest_run": runtime_coordinator.get("latest_run"),
                "runtime_coordinator_decisions": runtime_coordinator.get("runtime_coordinator_decisions", 0),
                "dry_run_coordinator_decisions": runtime_coordinator.get("dry_run_coordinator_decisions", 0),
                "runtime_coordinator_decisions_created_last_run": runtime_coordinator.get("runtime_coordinator_decisions_created_last_run", 0),
                "eligible_runtime_brain_outputs": runtime_coordinator.get("eligible_runtime_brain_outputs", 0),
                "no_trade_decisions": runtime_coordinator.get("no_trade_decisions", 0),
                "blocked_decisions": runtime_coordinator.get("blocked_decisions", 0),
                "hold_for_more_evidence_decisions": runtime_coordinator.get("hold_for_more_evidence_decisions", 0),
                "input_brain_output_count": runtime_coordinator.get("input_brain_output_count", 0),
                "remaining_blockers": runtime_coordinator.get("remaining_blockers", []),
                "paper_ready": False,
            },
            "orderbook": {
                "total_snapshots": orderbook.get("total_snapshots", 0),
                "fresh_snapshots": orderbook.get("fresh_snapshots", 0),
                "stale_snapshots": orderbook.get("stale_snapshots", 0),
                "ok_snapshots": orderbook.get("ok_snapshots", 0),
                "partial_snapshots": orderbook.get("partial_snapshots", 0),
                "empty_orderbooks": orderbook.get("empty_orderbooks", 0),
                "markets_with_orderbook": orderbook.get("markets_with_orderbook", 0),
                "orderbook_coverage_ratio": orderbook.get("orderbook_coverage_ratio", 0.0),
                "avg_spread": orderbook.get("avg_spread", 0.0),
                "avg_liquidity_score": orderbook.get("avg_liquidity_score", 0.0),
                "latest_collected_at": orderbook.get("latest_collected_at"),
                "paper_ready": False,
            },
            "market_binding": {
                "latest_run": market_binding.get("latest_run"),
                "total_signals": market_binding.get("total_signals", 0),
                "runtime_signals": market_binding.get("runtime_signals", 0),
                "signal_market_links": market_binding.get("signal_market_links", 0),
                "linked_runtime_signals": market_binding.get("linked_runtime_signals", 0),
                "unlinked_runtime_signals": market_binding.get("unlinked_runtime_signals", 0),
                "safe_links_created_last_run": market_binding.get("safe_links_created_last_run", 0),
                "suggestions_created_last_run": market_binding.get("suggestions_created_last_run", 0),
                "review_only_candidates": market_binding.get("review_only_candidates", 0),
                "blocked_weak_evidence": market_binding.get("blocked_weak_evidence", 0),
                "blocked_stale": market_binding.get("blocked_stale", 0),
                "blocked_dry_run": market_binding.get("blocked_dry_run", 0),
                "ambiguous_candidates": market_binding.get("ambiguous_candidates", 0),
                "link_coverage_ratio": market_binding.get("link_coverage_ratio", 0.0),
                "paper_ready": False,
            },
            "risk_core": {
                "latest_run": risk_core.get("latest_run"),
                "total_risk_decisions": risk_core.get("total_risk_decisions", 0),
                "approved_count": risk_core.get("approved_count", 0),
                "rejected_count": risk_core.get("rejected_count", 0),
                "blocked_count": risk_core.get("blocked_count", 0),
                "warning_count": risk_core.get("warning_count", 0),
                "avg_risk_score": risk_core.get("avg_risk_score", 0.0),
                "top_risk_blockers": risk_core.get("top_risk_blockers", []),
                "paper_candidate_allowed_count": risk_core.get("paper_candidate_allowed_count", 0),
                "risk_approved_count": risk_core.get("risk_approved_count", 0),
                "execution_allowed_count": risk_core.get("execution_allowed_count", 0),
                "paper_ready": False,
            },
            "exit_foundation": {
                "latest_run": exit_foundation.get("latest_run"),
                "total_exit_plans": exit_foundation.get("total_exit_plans", 0),
                "complete_exit_plans": exit_foundation.get("complete_exit_plans", 0),
                "incomplete_exit_plans": exit_foundation.get("incomplete_exit_plans", 0),
                "blocked_exit_plans": exit_foundation.get("blocked_exit_plans", 0),
                "paper_exit_ready_count": exit_foundation.get("paper_exit_ready_count", 0),
                "paper_intent_allowed_count": exit_foundation.get("paper_intent_allowed_count", 0),
                "execution_allowed_count": exit_foundation.get("execution_allowed_count", 0),
                "missing_market_count": exit_foundation.get("missing_market_count", 0),
                "missing_orderbook_count": exit_foundation.get("missing_orderbook_count", 0),
                "missing_side_count": exit_foundation.get("missing_side_count", 0),
                "missing_risk_approval_count": exit_foundation.get("missing_risk_approval_count", 0),
                "top_exit_blockers": exit_foundation.get("top_exit_blockers", []),
                "target_exit_count": exit_foundation.get("target_exit_count", 0),
                "stop_loss_count": exit_foundation.get("stop_loss_count", 0),
                "max_hold_seconds_default": exit_foundation.get("max_hold_seconds_default", 3600),
                "emergency_exit_rules_count": exit_foundation.get("emergency_exit_rules_count", 0),
                "liquidity_exit_check_count": exit_foundation.get("liquidity_exit_check_count", 0),
                "paper_ready": False,
            },
            "paper_eligibility": {
                "latest_run": paper_eligibility.get("latest_run"),
                "total_candidates": paper_eligibility.get("total_candidates", 0),
                "eligible_count": paper_eligibility.get("eligible_count", 0),
                "ineligible_count": paper_eligibility.get("ineligible_count", 0),
                "blocked_count": paper_eligibility.get("blocked_count", 0),
                "incomplete_count": paper_eligibility.get("incomplete_count", 0),
                "paper_intent_allowed_count": paper_eligibility.get("paper_intent_allowed_count", 0),
                "execution_allowed_count": paper_eligibility.get("execution_allowed_count", 0),
                "missing_exit_plan_count": paper_eligibility.get("missing_exit_plan_count", 0),
                "missing_risk_decision_count": paper_eligibility.get("missing_risk_decision_count", 0),
                "missing_thesis_count": paper_eligibility.get("missing_thesis_count", 0),
                "missing_market_count": paper_eligibility.get("missing_market_count", 0),
                "missing_orderbook_count": paper_eligibility.get("missing_orderbook_count", 0),
                "missing_binding_count": paper_eligibility.get("missing_binding_count", 0),
                "missing_lineage_count": paper_eligibility.get("missing_lineage_count", 0),
                "dry_run_blocked_count": paper_eligibility.get("dry_run_blocked_count", 0),
                "top_eligibility_blockers": paper_eligibility.get("top_eligibility_blockers", []),
                "paper_ready": False,
            },
            "paper_intents": {
                "latest_run": paper_intents.get("latest_run"),
                "candidates_checked": paper_intents.get("candidates_checked", 0),
                "eligible_candidates": paper_intents.get("eligible_candidates", 0),
                "total_paper_intents": paper_intents.get("total_paper_intents", 0),
                "created_intents": paper_intents.get("created_intents", 0),
                "paper_only_true_count": paper_intents.get("paper_only_true_count", 0),
                "live_true_count": paper_intents.get("live_true_count", 0),
                "execution_allowed_count": paper_intents.get("execution_allowed_count", 0),
                "order_intent_created_count": paper_intents.get("order_intent_created_count", 0),
                "no_trade_records_created": paper_intents.get("no_trade_records_created", 0),
                "accounted_candidates": paper_intents.get("accounted_candidates", 0),
                "unaccounted_candidates": paper_intents.get("unaccounted_candidates", 0),
                "paper_ready": False,
            },
            "no_trade": {
                "latest_run": no_trade.get("latest_run"),
                "total_no_trade_records": no_trade.get("total_no_trade_records", 0),
                "counts_by_category": no_trade.get("counts_by_category", []),
                "top_no_trade_reasons": no_trade.get("top_no_trade_reasons", []),
                "blocked_candidates": no_trade.get("blocked_candidates", 0),
                "missing_requirements_summary": no_trade.get("missing_requirements_summary", []),
                "unaccounted_candidates": no_trade.get("unaccounted_candidates", 0),
                "paper_ready": False,
            },
        }

    def _alerts(self, **layers: Any) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        errors = layers.pop("errors", [])
        for error in errors:
            alerts.append({"severity": "ERROR", "layer": "mesh", "message": error, "evidence": "dashboard/api/v2/mesh"})
        for name, payload in layers.items():
            if not isinstance(payload, dict):
                continue
            status = str(payload.get("status") or "").upper()
            if status in {"ERROR", "DEGRADED", "MISSING"}:
                alerts.append(
                    {
                        "severity": "ERROR" if status == "ERROR" else "WARN",
                        "layer": name,
                        "message": f"{name} layer status is {status}",
                        "evidence": f"dashboard/api/v2/{_layer_evidence_slug(name)}",
                    }
                )
        impact_graph = layers.get("impact_graph", {})
        if int(impact_graph.get("unlinked_signals") or 0) > 0:
            alerts.append(
                {
                    "severity": "WARN",
                    "layer": "impact_graph",
                    "message": f"{impact_graph.get('unlinked_signals')} signals are unlinked",
                    "evidence": "dashboard/api/v2/impact-graph",
                }
            )
        coordinator = layers.get("coordinator", {})
        if int(coordinator.get("execution_allowed_count") or 0) > 0:
            alerts.append(
                {
                    "severity": "ERROR",
                    "layer": "coordinator",
                    "message": "Coordinator has execution_allowed decisions",
                    "evidence": "dashboard/api/v2/coordinator",
                }
            )
        return alerts

    def _readiness(
        self,
        *,
        runtime: dict[str, Any],
        sources: dict[str, Any],
        neurons: dict[str, Any],
        signals: dict[str, Any],
        lineage: dict[str, Any],
        signal_quality: dict[str, Any],
        signal_processing: dict[str, Any],
        link_coverage: dict[str, Any],
        lineage_coverage: dict[str, Any],
        impact_graph: dict[str, Any],
        brain_outputs: dict[str, Any],
        coordinator: dict[str, Any],
        thesis: dict[str, Any],
        dry_run: dict[str, Any],
        dry_run_provenance: dict[str, Any],
        errors: list[str],
    ) -> dict[str, Any]:
        blocked_by: list[str] = []
        runtime_ok = runtime.get("healthy") is True
        source_ok = str(sources.get("status")) in {"OK", "DEGRADED", "EMPTY"}
        signals_ok = str(signals.get("status")) != "ERROR"
        data_ready = runtime_ok and source_ok and signals_ok

        if int(neurons.get("total_neurons") or 0) <= 0:
            blocked_by.append("neuron_registry_empty")
        if int(signals.get("signals_24h") or 0) <= 0:
            blocked_by.append("production_signals_24h_zero")
        if int(coordinator.get("execution_allowed_count") or 0) > 0:
            blocked_by.append("coordinator_execution_allowed_count_nonzero")
        if errors:
            blocked_by.append("mesh_endpoint_errors")
        mesh_ready = data_ready and not errors and int(neurons.get("total_neurons") or 0) > 0 and int(coordinator.get("execution_allowed_count") or 0) == 0

        orderbook_count = self._orderbook_snapshot_count()
        if orderbook_count == 0:
            blocked_by.append("orderbook_snapshots_zero")
        if int(brain_outputs.get("total_outputs_24h") or 0) == 0:
            blocked_by.append("production_brain_outputs_24h_zero")
        if not dry_run.get("latest_dry_run"):
            blocked_by.append("first_intelligence_dry_run_not_completed")
        if int(impact_graph.get("unlinked_signals") or 0) > 0:
            blocked_by.append("unlinked_signals_present")
        if int(signal_quality.get("total_evaluated") or 0) == 0:
            blocked_by.append("signal_quality_evaluations_zero")
        if int(signal_quality.get("can_feed_paper") or 0) == 0:
            blocked_by.append("signals_can_feed_paper_zero")
        if int(signal_processing.get("total") or 0) == 0:
            blocked_by.append("SIGNAL_PROCESSING_NOT_COMPLETE")
        if int(signal_processing.get("unprocessed_count") or 0) > 0:
            blocked_by.append("SIGNAL_PROCESSING_NOT_COMPLETE")
        if int(signal_processing.get("stale_count") or 0) > 0:
            blocked_by.append("SIGNALS_STALE")
        if int(signal_processing.get("rejected_count") or 0) > 0 or int(signal_processing.get("paper_eligible_informational_count") or 0) == 0:
            blocked_by.append("SIGNAL_QUALITY_GATE_BLOCKED")
        blockers = {str(item.get("blocker")) for item in signal_processing.get("top_gate_blockers", []) if isinstance(item, dict)}
        if {"linked_to_market", "production_market_link", "market_id"}.intersection(blockers):
            blocked_by.append("SIGNALS_NOT_LINKED")
        if int(link_coverage.get("total_analyzed") or 0) == 0:
            blocked_by.append("LINK_COVERAGE_ANALYSIS_MISSING")
        if int(link_coverage.get("unlinked_signals") or 0) > 0:
            blocked_by.append("SIGNALS_UNLINKED_HIGH")
        if float(link_coverage.get("link_coverage_ratio") or 0.0) < 0.8:
            blocked_by.append("SIGNAL_LINK_COVERAGE_LOW")
        if int(link_coverage.get("safe_to_link_count") or 0) > 0:
            blocked_by.append("LINKABLE_SIGNALS_PENDING_REVIEW")
        if int(link_coverage.get("weak_suggestions_count") or 0) > 0:
            blocked_by.append("LINK_SUGGESTIONS_WEAK_EVIDENCE")
        if int(link_coverage.get("dry_run_only_unlinked") or 0) > 0:
            blocked_by.append("DRY_RUN_LINKS_BLOCKED_FROM_PAPER")
        if int(lineage_coverage.get("total_analyzed") or 0) == 0:
            blocked_by.append("LINEAGE_ANALYSIS_MISSING")
        if int(lineage_coverage.get("unbound_signals") or 0) > 0:
            blocked_by.append("SIGNALS_UNBOUND_HIGH")
        if float(lineage_coverage.get("lineage_coverage_ratio") or 0.0) < 0.8:
            blocked_by.append("SIGNAL_LINEAGE_COVERAGE_LOW")
        if int(lineage_coverage.get("missing_producer_count") or 0) > 0:
            blocked_by.append("SIGNALS_MISSING_PRODUCER")
        if int(lineage_coverage.get("missing_source_count") or 0) > 0:
            blocked_by.append("SIGNALS_MISSING_SOURCE")
        if int(lineage_coverage.get("missing_raw_payload_ref_count") or 0) > 0:
            blocked_by.append("SIGNALS_MISSING_RAW_PAYLOAD_REF")
        if int(lineage_coverage.get("missing_correlation_id_count") or 0) > 0:
            blocked_by.append("SIGNALS_MISSING_CORRELATION_ID")
        if int(lineage_coverage.get("dry_run_only_signals") or 0) > 0:
            blocked_by.append("DRY_RUN_LINEAGE_BLOCKED_FROM_PAPER")
        if int(dry_run_provenance.get("total_analyzed") or 0) == 0:
            blocked_by.append("DRY_RUN_PROVENANCE_ANALYSIS_MISSING")
        if int(dry_run_provenance.get("brain_outputs_dry_run") or 0) > 0 and int(dry_run_provenance.get("brain_outputs_runtime") or 0) == 0:
            blocked_by.append("BRAIN_OUTPUTS_DRY_RUN_ONLY")
        if int(dry_run_provenance.get("coordinator_decisions_dry_run") or 0) > 0 and int(dry_run_provenance.get("coordinator_decisions_runtime") or 0) == 0:
            blocked_by.append("COORDINATOR_DECISIONS_DRY_RUN_ONLY")
        if int(dry_run_provenance.get("brain_outputs_dry_run") or 0) > 0 or int(dry_run_provenance.get("coordinator_decisions_dry_run") or 0) > 0:
            blocked_by.append("DRY_RUN_EVIDENCE_BLOCKED_FROM_PAPER")
        if int(dry_run_provenance.get("unknown_provenance_count") or 0) > 0:
            blocked_by.append("PROVENANCE_UNKNOWN")
        if runtime.get("mode_mismatch"):
            blocked_by.append("env_mode_differs_from_persisted_mode")
        if runtime.get("kill_switch_mismatch"):
            blocked_by.append("env_kill_switch_differs_from_persisted_kill_switch")
        if int(thesis.get("positions_without_thesis") or 0) > 0:
            blocked_by.append("positions_without_thesis")
        blocked_by.append("paper_full_evidence_loop_not_proven_in_part4a")
        blocked_by.append("paper_full_evidence_loop_not_proven_after_part4b")
        paper_ready = False
        return {
            "data_ready": bool(data_ready),
            "mesh_ready": bool(mesh_ready),
            "paper_ready": paper_ready,
            "blocked_by": sorted(set(blocked_by)),
            "next_best_action": "Review dry-run outputs, reduce unlinked signals, and build a non-executing paper-readiness evidence loop.",
        }

    def _orderbook_snapshot_count(self) -> int:
        if not self._factory.enabled:
            return 0
        try:
            with self._factory.connect() as conn:
                if not _table_exists(conn, "orderbook_snapshots"):
                    return 0
                row = conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots").fetchone()
                return int(row["count"] or 0)
        except Exception:
            return 0


def _signal_layer(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "OK" if int(summary.get("total_signals_24h") or 0) > 0 else "EMPTY",
        "mock_data": False,
        "signals_per_minute": summary.get("signals_per_minute", 0.0),
        "signals_24h": summary.get("total_signals_24h", 0),
        "total_signals_24h": summary.get("total_signals_24h", 0),
        "signals_by_neuron": summary.get("signals_by_neuron", []),
        "signals_by_market": [],
        "latest_signals": summary.get("latest_signals", []),
        "stale_signals": summary.get("stale_signals", []),
        "unprocessed_signals": summary.get("unprocessed_signals", 0),
    }


def _operator_status(name: str, payload: dict[str, Any], factory: DatabaseConnectionFactory) -> str:
    if not factory.enabled:
        return "DISABLED"
    text = " ".join(str(value).upper() for value in payload.values() if isinstance(value, str))
    if "ERROR" in text:
        return "ERROR"
    if any(token in text for token in ("DEGRADED", "STALE")):
        return "DEGRADED"
    if _has_nonzero_or_rows(payload):
        return "OK"
    return "EMPTY"


def _has_nonzero_or_rows(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_nonzero_or_rows(item) for item in value.values())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, (int, float, Decimal)):
        return float(value) > 0
    return False


def _infer_layer_status(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if isinstance(status, str):
        return status
    if payload.get("errors"):
        return "ERROR"
    if _has_nonzero_or_rows(payload):
        return "OK"
    return "EMPTY"


def _overall_status(errors: list[str], alerts: list[dict[str, Any]]) -> str:
    if errors or any(item.get("severity") == "ERROR" for item in alerts):
        return "ERROR"
    if alerts:
        return "DEGRADED"
    return "OK"


def _empty_sources(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "mock_data": False,
        "active_sources": 0,
        "degraded_sources": 0,
        "missing_sources": 0,
        "disabled_sources": 0,
        "source_errors": [],
        "latest_source_update": None,
        "sources": [],
    }


def _str_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _max_time(values: Any) -> str | None:
    timestamps: list[datetime] = []
    for value in values:
        if isinstance(value, datetime):
            timestamps.append(value if value.tzinfo else value.replace(tzinfo=UTC))
    return max(timestamps).isoformat() if timestamps else None


def _layer_evidence_slug(layer: str) -> str:
    return {
        "exit_layer": "exits",
        "no_trade": "no-trade",
        "impact_graph": "impact-graph",
        "brain_outputs": "brain-outputs",
        "dry_run": "mesh-dry-run",
        "dry_run_provenance": "dry-run-provenance",
        "mesh_blockers": "mesh-blockers",
        "producer_health": "producer-health",
        "runtime_producer_evidence": "runtime-producer-evidence",
        "runtime_brain": "runtime-brain",
        "runtime_coordinator": "runtime-coordinator",
        "market_binding": "market-binding",
        "link_coverage": "link-coverage",
        "lineage_coverage": "lineage-coverage",
    }.get(layer, layer.replace("_", "-"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value
