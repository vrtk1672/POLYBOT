from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from app.control_center.action_contract import ControlCenterActionRequest
from app.control_center.action_service import ControlCenterActionService
from app.control_center.candidate_explanations import CandidateExplanationLedgerService
from app.control_center.candidate_event_correlation import CandidateEventCorrelationService
from app.control_center.candidate_producer_freshness import CandidateProducerFreshnessService
from app.control_center.candidate_scoped_events import CandidateScopedEventsService
from app.control_center.decision_propagation_trace import DecisionPropagationTraceService
from app.control_center.eligible_intent_bridge import EligibleIntentBridgeService
from app.control_center.event_mesh_proof import EventMeshProofService
from app.control_center.full_monitor_run_service import FullMonitorRunService
from app.control_center.full_mesh_inquiry import FullMeshInquiryControlService
from app.control_center.mesh_evidence_bundle import MeshEvidenceBundleService
from app.control_center.market_universe_memory import MarketUniverseMemoryControlService
from app.control_center.multi_trigger_candidate_generation import MultiTriggerCandidateGenerationControlService
from app.control_center.orderbook_price_readiness import CandidatePricePathService, OrderbookPriceReadinessService
from app.control_center.paper_actionability import PaperActionabilityService
from app.control_center.paper_certification_plan import PaperCertificationPlanService
from app.control_center.paper_observation_policy import PaperObservationPolicyControlService
from app.control_center.paper_simulation import PaperSimulationControlService
from app.control_center.paper_readiness import PaperReadinessService
from app.control_center.pre_paper_safety import PrePaperSafetyService
from app.control_center.proactive_candidate_generation import ProactiveCandidateGenerationControlService
from app.control_center.proactive_seed_mesh_inquiry import ProactiveSeedMeshInquiryControlService
from app.control_center.query_service import ControlCenterQueryService
from app.control_center.research_priority_watchlist import ResearchPriorityWatchlistControlService
from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.source_backed_edge import SourceBackedEdgeControlService
from app.control_center.source_event_memory import SourceEventMemoryControlService
from app.control_center.source_refresh_status import SourceRefreshStatusService
from app.control_center.system_overview import SystemOverviewService
from app.control_center.targeted_market_revalidation import TargetedMarketRevalidationControlService
from app.control_center.runtime_supervisor import RuntimeSupervisorService
from app.control_center.runtime_supervisor_wiring import build_runtime_supervisor
from app.control_center.supervisor_life_path import SupervisorLifePathService
from app.control_center.static_serving import control_center_index_path, control_center_static_path
from app.control_center.truth_contract import control_center_truth_contract_demo
from app.control_center.trade_opportunity_score import TradeOpportunityScoreControlService
from app.config import get_settings
from app.runtime.state_governor import StateGovernor
from app.capital_brain.service import CapitalBrainService
from app.intelligence_sources.service import IntelligenceSourceReadinessService
from app.services.alerts import AlertEventService
from app.services.ai_mesh_intelligence import AIMarketIntelligenceMeshOrgan
from app.services.ai_context_router import AIContextRouterService
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_dialogue import BrainDialogueService
from app.services.brain_mesh_activation import BrainMeshActivationService
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.trade_thesis_engine import TradeThesisEngine
from app.services.trade_lifecycle import TradeLifecycleService
from app.services.brain_outputs import BrainOutputService
from app.services.candidate_eligibility_recovery import CandidateEligibilityRecoveryService
from app.services.clob_token_book_verification import ClobTokenBookVerificationService
from app.services.decision_autopsy import DecisionAutopsyService
from app.services.hunting_autopsy import HuntingAutopsyService
from app.services.dry_run_provenance import DryRunProvenanceService
from app.services.downstream_evidence_recompute import DownstreamEvidenceRecomputeService
from app.services.exit_foundation import ExitFoundationService
from app.services.exit_hold_reasoning import ExitHoldReasoningService
from app.services.evidence_refresh import EvidenceRefreshService
from app.services.fresh_market_identity import FreshMarketIdentityGateService
from app.services.freshness_governance import FreshnessGovernanceService
from app.services.fresh_seed_paper_path import FreshSeedPaperCandidateService
from app.services.impact_graph import ImpactGraphService
from app.services.link_coverage import LinkCoverageService
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.live_orderbook_watcher import LiveOrderbookWatcherService
from app.services.lineage_coverage import LineageCoverageService
from app.services.mesh_blockers import MeshBlockersService
from app.services.mesh_dashboard import MeshDashboardService
from app.services.mesh_dry_run import MeshDryRunService
from app.neural_bus.service import NeuralEventBusService
from app.mesh_sessions.service import MeshSessionService
from app.mesh_coordinator.service import MeshCoordinatorDecisionService
from app.multi_brain_consumption.service import MultiBrainConsumptionService
from app.position_awareness.service import PositionAwarenessService
from app.shared_awareness.service import SharedAwarenessService
from app.services.neuron_intelligence import NeuronIntelligenceService
from app.services.orderbook_snapshots import OrderbookSnapshotService
from app.services.open_position_watchdog import OpenPositionWatchdogService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.paper_dashboard_truth import PaperDashboardTruthService
from app.services.paper_trade_forensics import PaperTradeForensicsService
from app.services.paper_capital import PaperCapitalService
from app.services.paper_execution import PaperExecutionService
from app.services.paper_exit_loop import PaperExitLoopService
from app.services.paper_intents import PaperIntentGateService
from app.services.payout_odds import PayoutOddsService
from app.services.paper_lineage_quarantine import PaperLineageQuarantineService
from app.services.paper_defense import PaperDefenseGovernor
from app.services.paper_session import PaperSessionService
from app.services.same_market_arbitration import SameMarketSideArbitrator
from app.services.overnight_observation_status import OvernightObservationStatusService
from app.services.polymarket_binding import PolymarketIdentityBindingService
from app.services.polymarket_token_truth import PolymarketTokenTruthService
from app.services.post_side_risk_exit_readiness import PostSideRiskExitReadinessService
from app.services.producer_health import ProducerHealthService
from app.services.security_secrets import SecuritySecretsService
from app.services.same_market_side_guard import SameMarketSideGuardService
from app.services.query.dashboard_v2_query_service import DashboardV2QueryService
from app.services.query.operator_dashboard_query_service import OperatorDashboardQueryService
from app.services.neuron_registry import NeuronRegistryService
from app.services.opportunity_memory import OpportunityMemoryService
from app.services.opportunity_mesh_coordinator import OpportunityMeshCoordinator
from app.services.rules_resolution_truth import RulesResolutionTruthService
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
from app.services.runtime_coordinator import RuntimeCoordinatorDecisionService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService
from app.services.risk_core import RiskCoreService
from app.services.risk_evidence_mesh import RiskEvidenceMeshService
from app.services.side_evidence import DeterministicSideEvidenceService
from app.services.signal_market_binding import SignalMarketBindingRecoveryService
from app.services.signal_processing import SignalProcessingService
from app.services.signal_quality import SignalQualityService
from app.services.signal_lineage import SignalLineageService
from app.services.source_status import SourceStatusService
from app.source_to_neuron.service import SourceToNeuronIngestionService
from app.services.system_power import SystemPowerService
from app.services.telegram_bot import TelegramCommandService
from app.services.thesis_profiles import ThesisProfileService
from app.services.trusted_orderbook import TrustedOrderbookEvidenceService
from app.services.truth_state import TruthStateService


class RuntimeProducerEvidenceRunRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    producer_names: list[str] = Field(default_factory=list)
    dry_run: bool = False
    apply_evaluations: bool = True


class RuntimeBrainRunRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    min_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    write_outputs: bool = True


class RuntimeCoordinatorRunRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    min_brain_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    write_decisions: bool = True


class OrderbookSnapshotCollectRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    market_ids: list[str] = Field(default_factory=list)
    source: str = "auto"


class SignalMarketBindingRecoveryRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=500)
    apply_safe_links: bool = True
    create_suggestions: bool = True
    include_stale: bool = False
    include_dry_run: bool = False


class ThesisProfileBuildRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    include_incomplete: bool = True
    include_blocked: bool = True
    write_profiles: bool = True


class RiskCoreEvaluateRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    include_blocked: bool = True
    write_decisions: bool = True


class RiskEvidenceMeshEvaluateRequest(BaseModel):
    subject_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class PayoutOddsEvaluateRequest(BaseModel):
    subject_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class ExitHoldEvaluateRequest(BaseModel):
    subject_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class CapitalEfficiencyEvaluateRequest(BaseModel):
    subject_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class TradeLifecycleBuildRequest(BaseModel):
    subject_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class LifecycleGovernanceEvaluateRequest(BaseModel):
    subject_type: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class FreshnessGovernanceEvaluateRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class TruthStateAuditRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    dry_run: bool = False


class ExitPlanBuildRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    include_blocked: bool = True
    write_plans: bool = True


class PaperEligibilityEvaluateRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    include_blocked: bool = True
    write_candidates: bool = True


class PaperIntentBuildRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    write_intents: bool = True
    write_no_trade: bool = True


class PaperExitLoopRunRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    correlation_id: str | None = None


class PaperExecutionRunRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    cycle_id: str | None = None
    correlation_id: str | None = None


class PaperLineageQuarantineRunRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    actor: str = "codex"


class PaperSessionResetRequest(BaseModel):
    balance: float = Field(default=1000, gt=0)
    defense_level: int | None = Field(default=None, ge=0, le=100)
    start_after_reset: bool = False
    reason: str = "manual reset for new test session"
    created_by: str = "polybot-api"


class PaperDefenseUpdateRequest(BaseModel):
    defense_level: int = Field(ge=0, le=100)
    reason: str = "manual PAPER defense update"
    actor: str = "polybot-api"


class TrustedOrderbookResolveRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    cycle_id: str | None = None
    refresh_orderbooks: bool = True


class PolymarketBindingRecoveryRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    cycle_id: str | None = None
    refresh_orderbooks: bool = True
    apply_backfill: bool = True


class PolymarketTokenTruthRecoveryRequest(BaseModel):
    candidate_limit: int = Field(default=100, ge=1, le=500)
    gamma_market_limit: int = Field(default=20, ge=0, le=100)
    cycle_id: str | None = None
    verify_clob: bool = True
    apply_backfill: bool = True


class FreshMarketIdentityRecoveryRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    cycle_id: str | None = None
    dry_run: bool = True
    include_stale: bool = True


class ClobTokenBookVerificationRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    cycle_id: str | None = None
    seed_threshold: int = Field(default=5, ge=0, le=50)
    seed_limit: int = Field(default=20, ge=0, le=100)
    verify_seeds: bool = True


class LiveOrderbookWatcherRunRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=100)
    cycle_id: str | None = None
    dry_run: bool = False
    max_seconds: int = Field(default=30, ge=1, le=120)
    include_priority: int = Field(default=10, ge=1, le=10)


class OpenPositionWatchdogRunRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=100)
    cycle_id: str | None = None
    dry_run: bool = False
    max_seconds: int = Field(default=30, ge=1, le=120)


class FreshSeedPaperPathRunRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=100)
    cycle_id: str | None = None
    dry_run: bool = False
    max_seconds: int = Field(default=30, ge=1, le=120)


class NeuralReplayRequest(BaseModel):
    requested_by: str = "operator"
    reason: str = "manual neural event replay"
    event_type: str | None = None
    event_id: str | None = None
    start_id: int | None = Field(default=None, ge=1)
    end_id: int | None = Field(default=None, ge=1)
    market_id: str | None = None
    correlation_id: str | None = None
    limit: int = Field(default=1000, ge=1, le=5000)


class SourceToNeuronRunRequest(BaseModel):
    limit_per_source: int = Field(default=1, ge=1, le=10)
    include_ollama_generation: bool = True
    include_cloud_ai_generation: bool = True


def create_router() -> APIRouter:
    router = APIRouter()
    settings = get_settings()

    @router.get("/health")
    async def health(request: Request) -> dict:
        return await request.app.state.market_service.health()

    @router.get("/markets/top")
    async def top_markets(
        request: Request,
        limit: int | None = Query(default=None, ge=1, le=100),
    ) -> dict:
        items = await request.app.state.market_service.top_markets(limit=limit)
        serialized = [
            item.model_dump(mode="json", exclude={"market": {"raw_market": True}})
            for item in items
        ]
        return {"count": len(items), "items": serialized}

    @router.get("/markets/raw-count")
    async def raw_count(request: Request) -> dict:
        return await request.app.state.market_service.raw_counts()

    @router.get("/markets/last-refresh")
    async def last_refresh(request: Request) -> dict:
        return await request.app.state.market_service.last_refresh()

    @router.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_home() -> HTMLResponse:
        return HTMLResponse(_render_dashboard_html(settings.dashboard_title, settings.dashboard_refresh_seconds))

    @router.get("/control-center", response_class=HTMLResponse)
    async def control_center_home() -> Response:
        index_path = control_center_index_path()
        if index_path:
            return FileResponse(index_path)
        return HTMLResponse(_render_control_center_placeholder_html())

    @router.get("/control-center/{asset_path:path}")
    async def control_center_static_or_spa(asset_path: str) -> Response:
        static_path = control_center_static_path(asset_path)
        if static_path:
            return FileResponse(static_path)
        if asset_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Control Center asset not found")
        index_path = control_center_index_path()
        if index_path:
            return FileResponse(index_path)
        return HTMLResponse(_render_control_center_placeholder_html())

    @router.get("/dashboard/api/overview")
    async def dashboard_overview(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return OperatorDashboardQueryService().get_dashboard_overview(limit=limit)

    @router.get("/dashboard/api/health")
    async def dashboard_health() -> dict[str, object]:
        return OperatorDashboardQueryService().get_system_health()

    @router.get("/dashboard/api/kpi-quality")
    async def dashboard_kpi_quality(
        recent_cycles: int = Query(default=5, ge=1, le=50),
        top_reasons_limit: int = Query(default=5, ge=1, le=20),
    ) -> dict[str, object]:
        return OperatorDashboardQueryService().get_kpi_quality(
            recent_cycles=recent_cycles,
            top_reasons_limit=top_reasons_limit,
        )

    @router.get("/dashboard/api/ranking")
    async def dashboard_ranking(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return OperatorDashboardQueryService().get_ranking_overview(limit=limit)

    @router.get("/dashboard/api/positions-orders")
    async def dashboard_positions_orders(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return OperatorDashboardQueryService().get_positions_orders(limit=limit)

    @router.get("/dashboard/api/invalidation")
    async def dashboard_invalidation(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return OperatorDashboardQueryService().get_invalidation_exit_layers(limit=limit)

    @router.get("/dashboard/api/intelligence")
    async def dashboard_intelligence(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return OperatorDashboardQueryService().get_intelligence_panels(limit=limit)

    @router.get("/dashboard/api/audit")
    async def dashboard_audit(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return OperatorDashboardQueryService().get_audit_views(limit=limit)

    @router.get("/dashboard/api/alerts")
    async def dashboard_alerts(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return {"items": AlertEventService().list_recent_alerts(limit=limit)}

    @router.get("/dashboard/api/v2/overview")
    async def dashboard_v2_overview(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("overview", limit=limit)

    @router.get("/dashboard/api/v2/source-status")
    async def dashboard_v2_source_status() -> dict[str, object]:
        return SourceStatusService().get_dashboard_source_status()

    @router.get("/dashboard/api/v2/control/truth-contract")
    async def dashboard_v2_control_truth_contract() -> dict[str, object]:
        return control_center_truth_contract_demo()

    @router.get("/dashboard/api/v2/control/overview")
    async def dashboard_v2_control_overview() -> dict[str, object]:
        return ControlCenterQueryService().overview()

    @router.get("/dashboard/api/v2/control/organs")
    async def dashboard_v2_control_organs() -> dict[str, object]:
        return ControlCenterQueryService().organs()

    @router.get("/dashboard/api/v2/control/live-flow")
    async def dashboard_v2_control_live_flow() -> dict[str, object]:
        return ControlCenterQueryService().live_flow()

    @router.get("/dashboard/api/v2/control/decision-xray")
    async def dashboard_v2_control_decision_xray() -> dict[str, object]:
        return ControlCenterQueryService().decision_xray()

    @router.get("/dashboard/api/v2/control/blockers")
    async def dashboard_v2_control_blockers() -> dict[str, object]:
        return ControlCenterQueryService().blockers()

    @router.get("/dashboard/api/v2/control/closest-actionable")
    async def dashboard_v2_control_closest_actionable() -> dict[str, object]:
        return ControlCenterQueryService().closest_actionable()

    @router.get("/dashboard/api/v2/control/truth-state")
    async def dashboard_v2_control_truth_state() -> dict[str, object]:
        return ControlCenterQueryService().truth_state()

    @router.get("/dashboard/api/v2/control/risk-evidence")
    async def dashboard_v2_control_risk_evidence() -> dict[str, object]:
        return ControlCenterQueryService().risk_evidence()

    @router.get("/dashboard/api/v2/control/lifecycle-governance")
    async def dashboard_v2_control_lifecycle_governance() -> dict[str, object]:
        return ControlCenterQueryService().lifecycle_governance()

    @router.get("/dashboard/api/v2/control/mesh-dialogues")
    async def dashboard_v2_control_mesh_dialogues() -> dict[str, object]:
        return ControlCenterQueryService().mesh_dialogues()

    @router.get("/dashboard/api/v2/control/pnl-ledger")
    async def dashboard_v2_control_pnl_ledger() -> dict[str, object]:
        return ControlCenterQueryService().pnl_ledger()

    @router.get("/dashboard/api/v2/control/positions")
    async def dashboard_v2_control_positions() -> dict[str, object]:
        return ControlCenterQueryService().positions()

    @router.get("/dashboard/api/v2/control/no-trade")
    async def dashboard_v2_control_no_trade() -> dict[str, object]:
        return ControlCenterQueryService().no_trade()

    @router.get("/dashboard/api/v2/control/ai")
    async def dashboard_v2_control_ai() -> dict[str, object]:
        return ControlCenterQueryService().ai()

    @router.get("/dashboard/api/v2/control/logs")
    async def dashboard_v2_control_logs() -> dict[str, object]:
        return ControlCenterQueryService().logs()

    @router.get("/dashboard/api/v2/control/runtime-readiness")
    async def dashboard_v2_control_runtime_readiness() -> dict[str, object]:
        return RuntimeReadinessService().get_readiness()

    @router.get("/dashboard/api/v2/control/supervisor-life-path")
    async def dashboard_v2_control_supervisor_life_path() -> dict[str, object]:
        return SupervisorLifePathService().get_life_path()

    @router.get("/dashboard/api/v2/control/candidate-producer-freshness")
    async def dashboard_v2_control_candidate_producer_freshness() -> dict[str, object]:
        return CandidateProducerFreshnessService().get_freshness()

    @router.get("/dashboard/api/v2/control/paper-readiness")
    async def dashboard_v2_control_paper_readiness() -> dict[str, object]:
        return PaperReadinessService().get_readiness()

    @router.get("/dashboard/api/v2/control/candidate-explanations")
    async def dashboard_v2_control_candidate_explanations(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        status: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        blocker: str | None = None,
        final_outcome: str | None = None,
        freshness_state: str | None = None,
        include_evidence: bool = True,
        include_required_to_pass: bool = True,
    ) -> dict[str, object]:
        return CandidateExplanationLedgerService().list_explanations(
            limit=limit,
            offset=offset,
            status=status,
            market_id=market_id,
            side=side,
            blocker=blocker,
            final_outcome=final_outcome,
            freshness_state=freshness_state,
            include_evidence=include_evidence,
            include_required_to_pass=include_required_to_pass,
        )

    @router.get("/dashboard/api/v2/control/candidate-explanations/{candidate_id}")
    async def dashboard_v2_control_candidate_explanation(
        candidate_id: str,
        include_evidence: bool = True,
        include_required_to_pass: bool = True,
    ) -> dict[str, object]:
        payload = CandidateExplanationLedgerService().get_explanation(
            candidate_id,
            include_evidence=include_evidence,
            include_required_to_pass=include_required_to_pass,
        )
        if payload is None:
            raise HTTPException(status_code=404, detail={"status": "NOT_FOUND", "candidate_id": candidate_id})
        return payload

    @router.get("/dashboard/api/v2/control/eligible-intent-bridge")
    async def dashboard_v2_control_eligible_intent_bridge(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        outcome: str | None = None,
        bridge_state: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        include_ready: bool = True,
        include_blocked: bool = True,
        include_waiting: bool = True,
        include_existing_intents: bool = True,
    ) -> dict[str, object]:
        return EligibleIntentBridgeService().list_bridge(
            limit=limit,
            offset=offset,
            outcome=outcome,
            bridge_state=bridge_state,
            market_id=market_id,
            side=side,
            include_ready=include_ready,
            include_blocked=include_blocked,
            include_waiting=include_waiting,
            include_existing_intents=include_existing_intents,
        )

    @router.get("/dashboard/api/v2/control/eligible-intent-bridge/{candidate_id}")
    async def dashboard_v2_control_eligible_intent_bridge_candidate(candidate_id: str) -> dict[str, object]:
        payload = EligibleIntentBridgeService().get_bridge(candidate_id)
        if payload is None:
            raise HTTPException(status_code=404, detail={"status": "NOT_FOUND", "candidate_id": candidate_id})
        return payload

    @router.get("/dashboard/api/v2/control/orderbook-price-readiness")
    async def dashboard_v2_control_orderbook_price_readiness(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        market_id: str | None = None,
        candidate_id: str | None = None,
        side: str | None = None,
        state: str | None = None,
        freshness_state: str | None = None,
        include_candidates: bool = True,
        include_depth: bool = True,
        include_exit_liquidity: bool = True,
    ) -> dict[str, object]:
        return OrderbookPriceReadinessService().get_readiness(
            limit=limit,
            offset=offset,
            market_id=market_id,
            candidate_id=candidate_id,
            side=side,
            state=state,
            freshness_state=freshness_state,
            include_candidates=include_candidates,
            include_depth=include_depth,
            include_exit_liquidity=include_exit_liquidity,
        )

    @router.get("/dashboard/api/v2/control/orderbook-price-readiness/{candidate_id}")
    async def dashboard_v2_control_orderbook_price_readiness_candidate(candidate_id: str) -> dict[str, object]:
        payload = OrderbookPriceReadinessService().get_candidate(candidate_id)
        if payload is None:
            raise HTTPException(status_code=404, detail={"status": "NOT_FOUND", "candidate_id": candidate_id})
        return payload

    @router.get("/dashboard/api/v2/control/candidate-price-path")
    async def dashboard_v2_control_candidate_price_path(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        candidate_id: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        token_id: str | None = None,
        state: str | None = None,
        include_refresh_plan: bool = True,
        include_depth: bool = True,
        include_exit_liquidity: bool = True,
    ) -> dict[str, object]:
        return CandidatePricePathService().get_readiness(
            limit=limit,
            offset=offset,
            candidate_id=candidate_id,
            market_id=market_id,
            side=side,
            token_id=token_id,
            state=state,
            include_refresh_plan=include_refresh_plan,
            include_depth=include_depth,
            include_exit_liquidity=include_exit_liquidity,
        )

    @router.get("/dashboard/api/v2/control/candidate-price-path/{candidate_id}")
    async def dashboard_v2_control_candidate_price_path_candidate(candidate_id: str) -> dict[str, object]:
        payload = CandidatePricePathService().get_candidate(candidate_id)
        if payload is None:
            raise HTTPException(status_code=404, detail={"status": "NOT_FOUND", "candidate_id": candidate_id})
        return payload

    @router.get("/dashboard/api/v2/control/event-mesh-proof")
    async def dashboard_v2_control_event_mesh_proof(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        event_type: str = Query(default="orderbook.snapshot.created"),
        market_id: str | None = None,
        candidate_id: str | None = None,
        correlation_id: str | None = None,
        state: str | None = None,
        include_reactions: bool = True,
    ) -> dict[str, object]:
        return EventMeshProofService().list_proofs(
            limit=limit,
            offset=offset,
            event_type=event_type,
            market_id=market_id,
            candidate_id=candidate_id,
            correlation_id=correlation_id,
            state=state,
            include_reactions=include_reactions,
        )

    @router.get("/dashboard/api/v2/control/event-mesh-proof/{correlation_id}")
    async def dashboard_v2_control_event_mesh_proof_trace(correlation_id: str) -> dict[str, object]:
        payload = EventMeshProofService().get_trace(correlation_id)
        if payload is None:
            raise HTTPException(status_code=404, detail={"status": "NOT_FOUND", "correlation_id": correlation_id})
        return payload

    @router.get("/dashboard/api/v2/control/mesh-evidence-bundles")
    async def dashboard_v2_control_mesh_evidence_bundles(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        market_id: str | None = None,
        candidate_id: str | None = None,
        correlation_id: str | None = None,
        event_id: str | None = None,
        state: str | None = None,
        include_opinions: bool = True,
        include_conflicts: bool = True,
    ) -> dict[str, object]:
        return MeshEvidenceBundleService().list_bundles(
            limit=limit,
            offset=offset,
            market_id=market_id,
            candidate_id=candidate_id,
            correlation_id=correlation_id,
            event_id=event_id,
            state=state,
            include_opinions=include_opinions,
            include_conflicts=include_conflicts,
        )

    @router.get("/dashboard/api/v2/control/mesh-evidence-bundles/{correlation_id}")
    async def dashboard_v2_control_mesh_evidence_bundle(correlation_id: str) -> dict[str, object]:
        payload = MeshEvidenceBundleService().get_bundle(correlation_id)
        if payload is None:
            raise HTTPException(status_code=404, detail={"status": "NOT_FOUND", "correlation_id": correlation_id})
        return payload

    @router.get("/dashboard/api/v2/control/candidate-event-correlation")
    async def dashboard_v2_control_candidate_event_correlation(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        candidate_id: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        token_id: str | None = None,
        correlation_id: str | None = None,
        event_id: str | None = None,
        link_state: str | None = None,
        confidence: str | None = None,
        include_bundle: bool = True,
        include_candidates: bool = True,
    ) -> dict[str, object]:
        return CandidateEventCorrelationService().list_correlations(
            limit=limit,
            offset=offset,
            candidate_id=candidate_id,
            market_id=market_id,
            side=side,
            token_id=token_id,
            correlation_id=correlation_id,
            event_id=event_id,
            link_state=link_state,
            confidence=confidence,
            include_bundle=include_bundle,
            include_candidates=include_candidates,
        )

    @router.get("/dashboard/api/v2/control/candidate-event-correlation/{candidate_id}")
    async def dashboard_v2_control_candidate_event_correlation_candidate(candidate_id: str) -> dict[str, object]:
        payload = CandidateEventCorrelationService().get_candidate(candidate_id)
        if payload is None:
            raise HTTPException(status_code=404, detail={"status": "NOT_FOUND", "candidate_id": candidate_id})
        return payload

    @router.get("/dashboard/api/v2/control/candidate-scoped-events")
    async def dashboard_v2_control_candidate_scoped_events(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        return CandidateScopedEventsService().list_events(limit=limit, offset=offset, candidate_id=candidate_id)

    @router.get("/dashboard/api/v2/control/paper-actionability")
    async def dashboard_v2_control_paper_actionability(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        return PaperActionabilityService().list_actionability(limit=limit, offset=offset, candidate_id=candidate_id)

    @router.get("/dashboard/api/v2/control/pre-paper-safety")
    async def dashboard_v2_control_pre_paper_safety() -> dict[str, object]:
        return PrePaperSafetyService().get_safety()

    @router.get("/dashboard/api/v2/control/paper-certification-plan")
    async def dashboard_v2_control_paper_certification_plan() -> dict[str, object]:
        return PaperCertificationPlanService().get_plan()

    @router.get("/dashboard/api/v2/control/paper-session")
    async def dashboard_v2_control_paper_session() -> dict[str, object]:
        return PaperSessionService().status()

    @router.post("/dashboard/api/v2/control/paper-session/reset")
    async def dashboard_v2_control_paper_session_reset(payload: PaperSessionResetRequest) -> dict[str, object]:
        result = PaperSessionService().reset(balance=payload.balance, defense_level=payload.defense_level, reason=payload.reason, created_by=payload.created_by)
        if payload.start_after_reset and result.get("status") == "COMPLETED":
            action_payload = ControlCenterActionRequest(
                actor=payload.created_by,
                reason=f"Start PAPER after paper session reset: {payload.reason}",
                metadata={"requested_execution_mode": "PAPER", "paper_adapter": True, "live_adapter": False},
            )
            result["start_after_reset_result"] = ControlCenterActionService().execute("system-on", action_payload).to_api_dict()
        return result

    @router.get("/dashboard/api/v2/control/paper-session/history")
    async def dashboard_v2_control_paper_session_history(limit: int = Query(default=25, ge=1, le=100)) -> dict[str, object]:
        return PaperSessionService().history(limit=limit)

    @router.get("/dashboard/api/v2/control/paper-defense")
    async def dashboard_v2_control_paper_defense() -> dict[str, object]:
        return PaperDefenseGovernor().status()

    @router.post("/dashboard/api/v2/control/paper-defense")
    async def dashboard_v2_control_paper_defense_update(payload: PaperDefenseUpdateRequest) -> dict[str, object]:
        return PaperDefenseGovernor().set_defense_level(defense_level=payload.defense_level, reason=payload.reason, actor=payload.actor)

    @router.get("/dashboard/api/v2/control/paper-session/learning-report")
    async def dashboard_v2_control_paper_session_learning_report(session_id: str | None = None) -> dict[str, object]:
        return PaperDefenseGovernor().learning_report(session_id=session_id)

    @router.get("/dashboard/api/v2/control/paper-session/export")
    async def dashboard_v2_control_paper_session_export(session_id: str | None = None, format: str = Query(default="json", pattern="^(json|md|csv)$")) -> dict[str, object]:
        report = PaperDefenseGovernor().learning_report(session_id=session_id)
        paths = report.get("report_paths") if isinstance(report, dict) else None
        return {"status": report.get("status"), "format": format, "path": (paths or {}).get(format), "report_paths": paths}

    @router.get("/dashboard/api/v2/control/decision-autopsy")
    async def dashboard_v2_control_decision_autopsy(
        limit: int = Query(default=25, ge=1, le=250),
        paper_session_id: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        action: str | None = None,
        include_historical: bool = False,
    ) -> dict[str, object]:
        return DecisionAutopsyService().list_autopsies(
            limit=limit,
            paper_session_id=paper_session_id,
            market_id=market_id,
            side=side,
            action=action,
            include_historical=include_historical,
        )

    @router.get("/dashboard/api/v2/control/decision-autopsy/top-blockers")
    async def dashboard_v2_control_decision_autopsy_top_blockers(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DecisionAutopsyService().top_blockers(limit=limit)

    @router.get("/dashboard/api/v2/control/decision-autopsy/enter")
    async def dashboard_v2_control_decision_autopsy_enter(limit: int = Query(default=50, ge=1, le=250)) -> dict[str, object]:
        return DecisionAutopsyService().enter_autopsy(limit=limit)

    @router.get("/dashboard/api/v2/control/decision-autopsy/closest-actionable")
    async def dashboard_v2_control_decision_autopsy_closest_actionable(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DecisionAutopsyService().closest_actionable(limit=limit)

    @router.get("/dashboard/api/v2/control/supervisor-autopsy")
    async def dashboard_v2_control_supervisor_autopsy() -> dict[str, object]:
        return DecisionAutopsyService().supervisor_autopsy()

    @router.get("/dashboard/api/v2/control/paper-delta-autopsy")
    async def dashboard_v2_control_paper_delta_autopsy() -> dict[str, object]:
        return DecisionAutopsyService().paper_delta_autopsy()

    @router.get("/dashboard/api/v2/control/hunting-autopsy")
    async def dashboard_v2_control_hunting_autopsy() -> dict[str, object]:
        return HuntingAutopsyService().get_autopsy()

    @router.get("/dashboard/api/v2/control/arbitration-autopsy")
    async def dashboard_v2_control_arbitration_autopsy(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return SameMarketSideArbitrator().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/control/side-evidence")
    async def dashboard_v2_control_side_evidence(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DeterministicSideEvidenceService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/control/opportunity-mesh")
    async def dashboard_v2_control_opportunity_mesh(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return OpportunityMeshCoordinator().opportunity_mesh(limit=limit)

    @router.get("/dashboard/api/v2/control/intent-queue")
    async def dashboard_v2_control_intent_queue(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return OpportunityMeshCoordinator().intent_queue(limit=limit)

    @router.get("/dashboard/api/v2/control/candidate-consumption")
    async def dashboard_v2_control_candidate_consumption(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return OpportunityMeshCoordinator().candidate_consumption(limit=limit)

    @router.get("/dashboard/api/v2/control/opportunity-memory")
    async def dashboard_v2_control_opportunity_memory(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return OpportunityMemoryService().opportunity_memory(limit=limit)

    @router.get("/dashboard/api/v2/control/expired-intents")
    async def dashboard_v2_control_expired_intents(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return OpportunityMemoryService().expired_intents(limit=limit)

    @router.get("/dashboard/api/v2/control/paper-observation-policy")
    async def dashboard_v2_control_paper_observation_policy(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return PaperObservationPolicyControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/paper-observation-policy/refresh")
    async def dashboard_v2_control_paper_observation_policy_refresh(
        force: bool = False,
        limit: int = Query(default=500, ge=1, le=2000),
    ) -> dict[str, object]:
        return PaperObservationPolicyControlService().refresh(limit=limit, force=force)

    @router.get("/dashboard/api/v2/control/paper-observation-policy/by-seed")
    async def dashboard_v2_control_paper_observation_policy_by_seed(
        proactive_candidate_seed_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return PaperObservationPolicyControlService().by_seed(proactive_candidate_seed_id=proactive_candidate_seed_id, limit=limit)

    @router.get("/dashboard/api/v2/control/paper-observation-policy/by-market")
    async def dashboard_v2_control_paper_observation_policy_by_market(
        market_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return PaperObservationPolicyControlService().by_market(market_id=market_id, limit=limit)

    @router.get("/dashboard/api/v2/control/ai-mesh-intelligence")
    async def dashboard_v2_control_ai_mesh_intelligence(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return AIMarketIntelligenceMeshOrgan().summary(limit=limit)

    @router.post("/dashboard/api/v2/control/ai-mesh-intelligence/refresh")
    async def dashboard_v2_control_ai_mesh_intelligence_refresh(
        force: bool = False,
        limit: int = Query(default=12, ge=1, le=100),
    ) -> dict[str, object]:
        return AIMarketIntelligenceMeshOrgan().refresh(limit=limit, force=force)

    @router.get("/dashboard/api/v2/control/ai-mesh-intelligence/diagnostics")
    async def dashboard_v2_control_ai_mesh_intelligence_diagnostics() -> dict[str, object]:
        return AIMarketIntelligenceMeshOrgan().diagnostics()

    @router.post("/dashboard/api/v2/control/ai-mesh-intelligence/benchmark")
    async def dashboard_v2_control_ai_mesh_intelligence_benchmark(
        run_model_tests: bool = True,
    ) -> dict[str, object]:
        return AIMarketIntelligenceMeshOrgan().benchmark(run_model_tests=run_model_tests)

    @router.post("/dashboard/api/v2/control/ai-mesh-intelligence/benchmark-json")
    async def dashboard_v2_control_ai_mesh_intelligence_benchmark_json(
        run_model_tests: bool = True,
    ) -> dict[str, object]:
        return AIMarketIntelligenceMeshOrgan().benchmark_json(run_model_tests=run_model_tests)

    @router.get("/dashboard/api/v2/control/source-backed-edge")
    async def dashboard_v2_control_source_backed_edge(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        candidate_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object]:
        return SourceBackedEdgeControlService().list_edges(limit=limit, offset=offset, candidate_id=candidate_id, market_id=market_id)

    @router.get("/dashboard/api/v2/control/full-mesh-inquiry")
    async def dashboard_v2_control_full_mesh_inquiry(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        return FullMeshInquiryControlService().list_inquiries(limit=limit, offset=offset, candidate_id=candidate_id)

    @router.get("/dashboard/api/v2/control/source-refresh-status")
    async def dashboard_v2_control_source_refresh_status() -> dict[str, object]:
        return SourceRefreshStatusService().get_status()

    @router.get("/dashboard/api/v2/control/system-overview")
    async def dashboard_v2_control_system_overview() -> dict[str, object]:
        return SystemOverviewService().get_overview()

    @router.get("/dashboard/api/v2/control/decision-propagation-trace")
    async def dashboard_v2_control_decision_propagation_trace(
        limit: int = Query(default=20, ge=1, le=100),
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        return DecisionPropagationTraceService().get_trace(limit=limit, candidate_id=candidate_id)

    @router.get("/dashboard/api/v2/control/trade-opportunity-score")
    async def dashboard_v2_control_trade_opportunity_score(
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        return TradeOpportunityScoreControlService().list_scores(limit=limit, offset=offset, candidate_id=candidate_id)

    @router.get("/dashboard/api/v2/control/trade-thesis")
    async def dashboard_v2_control_trade_thesis(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return TradeThesisEngine().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/control/market-universe-memory")
    async def dashboard_v2_control_market_universe_memory(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return MarketUniverseMemoryControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/market-universe-memory/refresh")
    async def dashboard_v2_control_market_universe_memory_refresh(
        force: bool = False,
        limit: int | None = Query(default=None, ge=1, le=1000),
    ) -> dict[str, object]:
        return MarketUniverseMemoryControlService().refresh(force=force, limit=limit)

    @router.get("/dashboard/api/v2/control/market-universe-memory/lookup")
    async def dashboard_v2_control_market_universe_memory_lookup(
        market_id: str | None = None,
        condition_id: str | None = None,
        token_id: str | None = None,
        slug: str | None = None,
        title: str | None = None,
    ) -> dict[str, object]:
        return MarketUniverseMemoryControlService().lookup(
            market_id=market_id,
            condition_id=condition_id,
            token_id=token_id,
            slug=slug,
            title=title,
        )

    @router.get("/dashboard/api/v2/control/source-event-memory")
    async def dashboard_v2_control_source_event_memory(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return SourceEventMemoryControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/source-event-memory/refresh")
    async def dashboard_v2_control_source_event_memory_refresh(
        force: bool = False,
        window_hours: int = Query(default=72, ge=1, le=720),
        limit: int = Query(default=500, ge=1, le=2000),
    ) -> dict[str, object]:
        return SourceEventMemoryControlService().refresh(force=force, window_hours=window_hours, limit=limit)

    @router.get("/dashboard/api/v2/control/source-event-memory/recall")
    async def dashboard_v2_control_source_event_memory_recall(source_event_id: str) -> dict[str, object]:
        return SourceEventMemoryControlService().recall(source_event_id=source_event_id)

    @router.get("/dashboard/api/v2/control/source-event-memory/by-market")
    async def dashboard_v2_control_source_event_memory_by_market(
        market_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return SourceEventMemoryControlService().by_market(market_id=market_id, limit=limit)

    @router.get("/dashboard/api/v2/control/source-event-memory/linker-diagnostics")
    async def dashboard_v2_control_source_event_memory_linker_diagnostics() -> dict[str, object]:
        return SourceEventMemoryControlService().linker_diagnostics()

    @router.get("/dashboard/api/v2/control/targeted-market-revalidation")
    async def dashboard_v2_control_targeted_market_revalidation(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return TargetedMarketRevalidationControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/targeted-market-revalidation/refresh")
    async def dashboard_v2_control_targeted_market_revalidation_refresh(
        force: bool = False,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, object]:
        return TargetedMarketRevalidationControlService().refresh(limit=limit, force=force)

    @router.get("/dashboard/api/v2/control/targeted-market-revalidation/by-market")
    async def dashboard_v2_control_targeted_market_revalidation_by_market(
        market_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return TargetedMarketRevalidationControlService().by_market(market_id=market_id, limit=limit)

    @router.get("/dashboard/api/v2/control/targeted-market-revalidation/by-event")
    async def dashboard_v2_control_targeted_market_revalidation_by_event(
        source_event_id: str,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, object]:
        return TargetedMarketRevalidationControlService().by_event(source_event_id=source_event_id, limit=limit)

    @router.get("/dashboard/api/v2/control/proactive-candidate-generation")
    async def dashboard_v2_control_proactive_candidate_generation(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return ProactiveCandidateGenerationControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/proactive-candidate-generation/refresh")
    async def dashboard_v2_control_proactive_candidate_generation_refresh(
        force: bool = False,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, object]:
        return ProactiveCandidateGenerationControlService().refresh(limit=limit, force=force)

    @router.get("/dashboard/api/v2/control/proactive-candidate-generation/by-market")
    async def dashboard_v2_control_proactive_candidate_generation_by_market(
        market_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return ProactiveCandidateGenerationControlService().by_market(market_id=market_id, limit=limit)

    @router.get("/dashboard/api/v2/control/proactive-candidate-generation/by-event")
    async def dashboard_v2_control_proactive_candidate_generation_by_event(
        source_event_id: str,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, object]:
        return ProactiveCandidateGenerationControlService().by_event(source_event_id=source_event_id, limit=limit)

    @router.get("/dashboard/api/v2/control/proactive-candidate-generation/by-seed")
    async def dashboard_v2_control_proactive_candidate_generation_by_seed(proactive_candidate_seed_id: str) -> dict[str, object]:
        return ProactiveCandidateGenerationControlService().by_seed(proactive_candidate_seed_id=proactive_candidate_seed_id)

    @router.get("/dashboard/api/v2/control/multi-trigger-candidate-generation")
    async def dashboard_v2_control_multi_trigger_candidate_generation(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return MultiTriggerCandidateGenerationControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/multi-trigger-candidate-generation/refresh")
    async def dashboard_v2_control_multi_trigger_candidate_generation_refresh(
        force: bool = False,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, object]:
        return MultiTriggerCandidateGenerationControlService().refresh(limit=limit, force=force)

    @router.get("/dashboard/api/v2/control/multi-trigger-candidate-generation/by-market")
    async def dashboard_v2_control_multi_trigger_candidate_generation_by_market(
        market_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return MultiTriggerCandidateGenerationControlService().by_market(market_id=market_id, limit=limit)

    @router.get("/dashboard/api/v2/control/multi-trigger-candidate-generation/by-trigger")
    async def dashboard_v2_control_multi_trigger_candidate_generation_by_trigger(multi_trigger_id: str) -> dict[str, object]:
        return MultiTriggerCandidateGenerationControlService().by_trigger(multi_trigger_id=multi_trigger_id)

    @router.get("/dashboard/api/v2/control/research-priority-watchlist")
    async def dashboard_v2_control_research_priority_watchlist(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return ResearchPriorityWatchlistControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/research-priority-watchlist/refresh")
    async def dashboard_v2_control_research_priority_watchlist_refresh(
        force: bool = False,
        limit: int = Query(default=500, ge=1, le=2000),
    ) -> dict[str, object]:
        return ResearchPriorityWatchlistControlService().refresh(limit=limit, force=force)

    @router.get("/dashboard/api/v2/control/research-priority-watchlist/by-market")
    async def dashboard_v2_control_research_priority_watchlist_by_market(market_id: str) -> dict[str, object]:
        return ResearchPriorityWatchlistControlService().by_market(market_id=market_id)

    @router.get("/dashboard/api/v2/control/research-priority-watchlist/due")
    async def dashboard_v2_control_research_priority_watchlist_due(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return ResearchPriorityWatchlistControlService().due(limit=limit)

    @router.get("/dashboard/api/v2/control/proactive-seed-mesh-inquiry")
    async def dashboard_v2_control_proactive_seed_mesh_inquiry(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return ProactiveSeedMeshInquiryControlService().get_summary(limit=limit)

    @router.post("/dashboard/api/v2/control/proactive-seed-mesh-inquiry/refresh")
    async def dashboard_v2_control_proactive_seed_mesh_inquiry_refresh(
        force: bool = False,
        limit: int = Query(default=50, ge=1, le=500),
    ) -> dict[str, object]:
        return ProactiveSeedMeshInquiryControlService().refresh(limit=limit, force=force)

    @router.post("/dashboard/api/v2/control/proactive-seed-mesh-inquiry/run-adapter")
    async def dashboard_v2_control_proactive_seed_mesh_inquiry_run_adapter(
        force: bool = False,
        limit: int = Query(default=25, ge=1, le=250),
    ) -> dict[str, object]:
        return ProactiveSeedMeshInquiryControlService().run_adapter(limit=limit, force=force)

    @router.get("/dashboard/api/v2/control/proactive-seed-mesh-inquiry/adapter-diagnostics")
    async def dashboard_v2_control_proactive_seed_mesh_inquiry_adapter_diagnostics() -> dict[str, object]:
        return ProactiveSeedMeshInquiryControlService().adapter_diagnostics()

    @router.get("/dashboard/api/v2/control/proactive-seed-mesh-inquiry/by-seed")
    async def dashboard_v2_control_proactive_seed_mesh_inquiry_by_seed(
        proactive_candidate_seed_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return ProactiveSeedMeshInquiryControlService().by_seed(proactive_candidate_seed_id=proactive_candidate_seed_id, limit=limit)

    @router.get("/dashboard/api/v2/control/proactive-seed-mesh-inquiry/by-market")
    async def dashboard_v2_control_proactive_seed_mesh_inquiry_by_market(
        market_id: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        return ProactiveSeedMeshInquiryControlService().by_market(market_id=market_id, limit=limit)

    @router.get("/dashboard/api/v2/control/proactive-seed-mesh-inquiry/by-event")
    async def dashboard_v2_control_proactive_seed_mesh_inquiry_by_event(
        source_event_id: str,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, object]:
        return ProactiveSeedMeshInquiryControlService().by_event(source_event_id=source_event_id, limit=limit)

    @router.post("/dashboard/api/v2/control/actions/{action_name}")
    async def dashboard_v2_control_action(action_name: str, payload: ControlCenterActionRequest, request: Request) -> dict[str, object]:
        governor = StateGovernor()
        return ControlCenterActionService(
            governor=governor,
            runtime_supervisor=build_runtime_supervisor(governor=governor),
        ).execute(action_name, payload).model_dump(mode="json")

    @router.get("/dashboard/api/v2/control/full-monitor-run")
    async def dashboard_v2_control_full_monitor_run() -> dict[str, object]:
        return FullMonitorRunService().status()

    @router.get("/dashboard/api/v2/control/runtime-supervisor")
    async def dashboard_v2_control_runtime_supervisor() -> dict[str, object]:
        return RuntimeSupervisorService().status()

    @router.get("/dashboard/api/v2/control/paper-simulation")
    async def dashboard_v2_control_paper_simulation() -> dict[str, object]:
        return PaperSimulationControlService().status()

    @router.get("/dashboard/api/v2/system-power")
    async def dashboard_v2_system_power() -> dict[str, object]:
        return SystemPowerService().get_dashboard_summary()

    @router.get("/dashboard/api/v2/brain-mesh-activation")
    async def dashboard_v2_brain_mesh_activation(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return BrainMeshActivationService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/evidence-refresh")
    async def dashboard_v2_evidence_refresh(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return EvidenceRefreshService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/side-evidence")
    async def dashboard_v2_side_evidence(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DeterministicSideEvidenceService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/downstream-recompute")
    async def dashboard_v2_downstream_recompute(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DownstreamEvidenceRecomputeService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/eligibility-recovery")
    async def dashboard_v2_eligibility_recovery(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return CandidateEligibilityRecoveryService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/risk-exit-readiness")
    async def dashboard_v2_risk_exit_readiness(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return PostSideRiskExitReadinessService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/trusted-orderbook")
    async def dashboard_v2_trusted_orderbook(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return TrustedOrderbookEvidenceService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/orderbook-blockers")
    async def dashboard_v2_orderbook_blockers(limit: int = Query(default=50, ge=1, le=100)) -> dict[str, object]:
        return TrustedOrderbookEvidenceService().get_blocker_dashboard(limit=limit)

    @router.get("/dashboard/api/v2/polymarket-binding")
    async def dashboard_v2_polymarket_binding(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return PolymarketIdentityBindingService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/polymarket-token-truth")
    async def dashboard_v2_polymarket_token_truth(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return PolymarketTokenTruthService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/fresh-market-identity")
    async def dashboard_v2_fresh_market_identity(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return FreshMarketIdentityGateService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/clob-token-book-verification")
    async def dashboard_v2_clob_token_book_verification(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return ClobTokenBookVerificationService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/live-orderbook-watcher")
    async def dashboard_v2_live_orderbook_watcher(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return LiveOrderbookWatcherService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/open-position-watchdog")
    async def dashboard_v2_open_position_watchdog(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return OpenPositionWatchdogService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/open-position-watchdog/{paper_position_id}")
    async def dashboard_v2_open_position_watchdog_detail(
        paper_position_id: str,
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, object]:
        return OpenPositionWatchdogService().get_position_detail(paper_position_id, limit=limit)

    @router.get("/dashboard/api/v2/fresh-seed-paper-path")
    async def dashboard_v2_fresh_seed_paper_path(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return FreshSeedPaperCandidateService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/security/secrets")
    async def dashboard_v2_security_secrets(limit: int = Query(default=100, ge=1, le=200)) -> dict[str, object]:
        return SecuritySecretsService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/neuron-intelligence")
    async def dashboard_v2_neuron_intelligence(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return NeuronIntelligenceService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/neural-bus")
    async def dashboard_v2_neural_bus(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return NeuralEventBusService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/mesh-sessions")
    async def dashboard_v2_mesh_sessions(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return MeshSessionService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/mesh-sessions/{session_id}")
    async def dashboard_v2_mesh_session_detail(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        payload = MeshSessionService().session_detail(session_id, limit=limit)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Mesh session not found")
        return payload

    @router.get("/dashboard/api/v2/shared-awareness")
    async def dashboard_v2_shared_awareness(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return SharedAwarenessService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/shared-awareness/{session_id}")
    async def dashboard_v2_shared_awareness_detail(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        payload = SharedAwarenessService().detail(session_id, limit=limit)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Shared awareness not found")
        return payload

    @router.get("/dashboard/api/v2/multi-brain-consumption")
    async def dashboard_v2_multi_brain_consumption(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return MultiBrainConsumptionService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/multi-brain-consumption/{session_id}")
    async def dashboard_v2_multi_brain_consumption_detail(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        payload = MultiBrainConsumptionService().detail(session_id, limit=limit)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Multi-brain consumption session not found")
        return payload

    @router.get("/dashboard/api/v2/mesh-coordinator")
    async def dashboard_v2_mesh_coordinator(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return MeshCoordinatorDecisionService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/mesh-coordinator/session/{session_id}")
    async def dashboard_v2_mesh_coordinator_session(session_id: str) -> dict[str, object]:
        payload = MeshCoordinatorDecisionService().latest_for_session(session_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Mesh coordinator decision not found for session")
        return payload

    @router.get("/dashboard/api/v2/mesh-coordinator/{decision_id}")
    async def dashboard_v2_mesh_coordinator_detail(decision_id: str) -> dict[str, object]:
        payload = MeshCoordinatorDecisionService().detail(decision_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Mesh coordinator decision not found")
        return payload

    @router.get("/dashboard/api/v2/capital-brain")
    async def dashboard_v2_capital_brain(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return CapitalBrainService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/capital-brain/session/{session_id}")
    async def dashboard_v2_capital_brain_session(session_id: str) -> dict[str, object]:
        payload = CapitalBrainService().latest_for_session(session_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Capital Brain evaluation not found for session")
        return payload

    @router.get("/dashboard/api/v2/capital-brain/{evaluation_id}")
    async def dashboard_v2_capital_brain_detail(evaluation_id: str) -> dict[str, object]:
        payload = CapitalBrainService().detail(evaluation_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Capital Brain evaluation not found")
        return payload

    @router.get("/dashboard/api/v2/positions-awareness")
    async def dashboard_v2_positions_awareness(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return PositionAwarenessService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/positions-awareness/{position_id}")
    async def dashboard_v2_positions_awareness_detail(
        position_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        payload = PositionAwarenessService().detail(position_id, limit=limit)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Position awareness not found")
        return payload

    @router.get("/dashboard/api/v2/intelligence-sources")
    async def dashboard_v2_intelligence_sources(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return IntelligenceSourceReadinessService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/intelligence-sources/requirements")
    async def dashboard_v2_intelligence_source_requirements() -> dict[str, object]:
        return IntelligenceSourceReadinessService().requirements_report()

    @router.get("/dashboard/api/v2/intelligence-sources/health")
    async def dashboard_v2_intelligence_source_health() -> dict[str, object]:
        return IntelligenceSourceReadinessService().health_report()

    @router.post("/intelligence-sources/validate")
    async def validate_intelligence_sources() -> dict[str, object]:
        return IntelligenceSourceReadinessService().validate_endpoint()

    @router.get("/dashboard/api/v2/source-to-neuron-flow")
    async def dashboard_v2_source_to_neuron_flow(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return SourceToNeuronIngestionService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/ai-context-router")
    async def dashboard_v2_ai_context_router(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return AIContextRouterService().dashboard_summary(limit=limit)

    @router.post("/source-to-neuron/run")
    async def source_to_neuron_run(payload: SourceToNeuronRunRequest) -> dict[str, object]:
        return SourceToNeuronIngestionService().run_once(
            limit_per_source=payload.limit_per_source,
            include_ollama_generation=payload.include_ollama_generation,
            include_cloud_ai_generation=payload.include_cloud_ai_generation,
        )

    @router.get("/dashboard/api/v2/brain-dialogue")
    async def dashboard_v2_brain_dialogue(
        limit: int = Query(default=100, ge=1, le=500),
        component: str | None = None,
        market_id: str | None = None,
        candidate_id: str | None = None,
        paper_position_id: str | None = None,
        severity: str | None = None,
        component_type: str | None = None,
        status: str | None = None,
        silent: bool | None = None,
        since: str | None = None,
    ) -> dict[str, object]:
        return BrainDialogueService().list_events(
            limit=limit,
            component=component,
            market_id=market_id,
            candidate_id=candidate_id,
            paper_position_id=paper_position_id,
            severity=severity,
            component_type=component_type,
            status=status,
            silent=silent,
            since=since,
        )

    @router.get("/dashboard/api/v2/system-life")
    async def dashboard_v2_system_life() -> dict[str, object]:
        return BrainDialogueService().get_system_life()

    @router.get("/dashboard/api/v2/neuron-dialogue")
    async def dashboard_v2_neuron_dialogue(
        limit: int = Query(default=100, ge=1, le=500),
        component: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        return BrainDialogueService().get_neuron_dialogue(limit=limit, component=component, status=status)

    @router.get("/dashboard/api/v2/brain-dialogue/{candidate_id}")
    async def dashboard_v2_brain_dialogue_candidate(
        candidate_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        return BrainDialogueService().get_candidate_dialogue(candidate_id, limit=limit)

    @router.get("/dashboard/api/v2/rules")
    async def dashboard_v2_rules(limit: int = Query(default=25, ge=1, le=100)) -> dict[str, object]:
        return RulesResolutionTruthService().get_dashboard_rules_status(limit=limit)

    @router.get("/dashboard/api/v2/events")
    async def dashboard_v2_events(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("events", limit=limit)

    @router.post("/neural-bus/replay")
    async def neural_bus_replay(payload: NeuralReplayRequest) -> dict[str, object]:
        try:
            return NeuralEventBusService().replay_events(
                requested_by=payload.requested_by,
                reason=payload.reason,
                event_type=payload.event_type,
                event_id=payload.event_id,
                start_id=payload.start_id,
                end_id=payload.end_id,
                market_id=payload.market_id,
                correlation_id=payload.correlation_id,
                limit=payload.limit,
            )
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/dashboard/api/v2/signals")
    async def dashboard_v2_signals(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("signals", limit=limit)

    @router.get("/dashboard/api/v2/neurons")
    async def dashboard_v2_neurons() -> dict[str, object]:
        return NeuronRegistryService().get_neuron_mesh_summary()

    @router.get("/dashboard/api/v2/signal-lineage")
    async def dashboard_v2_signal_lineage(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return SignalLineageService().get_lineage_summary(limit=limit)

    @router.get("/dashboard/api/v2/signal-quality")
    async def dashboard_v2_signal_quality(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return SignalQualityService().get_signal_quality_summary(limit=limit)

    @router.get("/dashboard/api/v2/signal-processing")
    async def dashboard_v2_signal_processing(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return SignalProcessingService().get_signal_processing_summary(limit=limit)

    @router.get("/dashboard/api/v2/link-coverage")
    async def dashboard_v2_link_coverage(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return LinkCoverageService().get_link_coverage_summary(limit=limit)

    @router.get("/dashboard/api/v2/lineage-coverage")
    async def dashboard_v2_lineage_coverage(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return LineageCoverageService().get_lineage_coverage_summary(limit=limit)

    @router.get("/dashboard/api/v2/dry-run-provenance")
    async def dashboard_v2_dry_run_provenance(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return DryRunProvenanceService().get_summary(limit=limit)

    @router.get("/dashboard/api/v2/mesh-blockers")
    async def dashboard_v2_mesh_blockers(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return MeshBlockersService().get_mesh_blockers(limit=limit)

    @router.get("/dashboard/api/v2/producer-health")
    async def dashboard_v2_producer_health(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return ProducerHealthService().get_producer_health_summary(limit=limit)

    @router.get("/dashboard/api/v2/runtime-producer-evidence")
    async def dashboard_v2_runtime_producer_evidence(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return RuntimeProducerEvidenceService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/runtime-brain")
    async def dashboard_v2_runtime_brain(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return RuntimeBrainAdapterService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/runtime-coordinator")
    async def dashboard_v2_runtime_coordinator(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return RuntimeCoordinatorDecisionService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/orderbook")
    async def dashboard_v2_orderbook(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return OrderbookSnapshotService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/market-binding")
    async def dashboard_v2_market_binding(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return SignalMarketBindingRecoveryService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/thesis")
    async def dashboard_v2_thesis_profiles(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return ThesisProfileService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/risk-core")
    async def dashboard_v2_risk_core(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return RiskCoreService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/exit-foundation")
    async def dashboard_v2_exit_foundation(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return ExitFoundationService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/paper-eligibility")
    async def dashboard_v2_paper_eligibility(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PaperEligibilityService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/paper")
    async def dashboard_v2_paper(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PaperDashboardTruthService().get_summary(limit=limit)

    @router.get("/dashboard/api/v2/paper/positions")
    async def dashboard_v2_paper_positions(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return PaperDashboardTruthService().get_positions(limit=limit)

    @router.get("/dashboard/api/v2/paper/trade-forensics")
    async def dashboard_v2_paper_trade_forensics(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return PaperTradeForensicsService().list_trades(limit=limit)

    @router.get("/dashboard/api/v2/paper/trade-forensics/{paper_position_id}")
    async def dashboard_v2_paper_trade_forensics_detail(paper_position_id: str) -> dict[str, object]:
        payload = PaperTradeForensicsService().get_trade(paper_position_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Paper position not found")
        return payload

    @router.get("/dashboard/api/v2/paper/pnl")
    async def dashboard_v2_paper_unified_pnl(limit: int = Query(default=30, ge=1, le=365)) -> dict[str, object]:
        return PaperDashboardTruthService().get_pnl(limit=limit)

    @router.get("/dashboard/api/v2/paper/soak-readiness")
    async def dashboard_v2_paper_soak_readiness() -> dict[str, object]:
        return PaperDashboardTruthService().get_soak_readiness()

    @router.get("/dashboard/api/v2/paper/capital")
    async def dashboard_v2_paper_capital(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return PaperCapitalService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/same-market-side-guard")
    async def dashboard_v2_same_market_side_guard(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return SameMarketSideGuardService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/same-market-side-guard/{market_id}")
    async def dashboard_v2_same_market_side_guard_detail(
        market_id: str,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, object]:
        return SameMarketSideGuardService().get_market_detail(market_id, limit=limit)

    @router.get("/dashboard/api/v2/payout-odds")
    async def dashboard_v2_payout_odds(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PayoutOddsService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/payout-odds/{evaluation_id}")
    async def dashboard_v2_payout_odds_detail(evaluation_id: str) -> dict[str, object]:
        payload = PayoutOddsService().detail(evaluation_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Payout/odds evaluation not found")
        return payload

    @router.get("/dashboard/api/v2/exit-hold")
    async def dashboard_v2_exit_hold(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return ExitHoldReasoningService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/exit-hold/{evaluation_id}")
    async def dashboard_v2_exit_hold_detail(evaluation_id: str) -> dict[str, object]:
        payload = ExitHoldReasoningService().detail(evaluation_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Exit/Hold evaluation not found")
        return payload

    @router.get("/dashboard/api/v2/capital-efficiency")
    async def dashboard_v2_capital_efficiency(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return CapitalEfficiencyService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/capital-efficiency/{evaluation_id}")
    async def dashboard_v2_capital_efficiency_detail(evaluation_id: str) -> dict[str, object]:
        payload = CapitalEfficiencyService().detail(evaluation_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Capital efficiency evaluation not found")
        return payload

    @router.get("/dashboard/api/v2/trade-thesis")
    async def dashboard_v2_trade_thesis(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return TradeThesisEngine().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/trade-lifecycle")
    async def dashboard_v2_trade_lifecycle(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return TradeLifecycleService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/trade-lifecycle/{plan_id}")
    async def dashboard_v2_trade_lifecycle_detail(plan_id: str) -> dict[str, object]:
        payload = TradeLifecycleService().detail(plan_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Trade lifecycle plan not found")
        return payload

    @router.get("/dashboard/api/v2/lifecycle-governance")
    async def dashboard_v2_lifecycle_governance(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return LifecycleGovernanceGateService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/lifecycle-governance/{decision_id}")
    async def dashboard_v2_lifecycle_governance_detail(decision_id: str) -> dict[str, object]:
        payload = LifecycleGovernanceGateService().detail(decision_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Lifecycle governance decision not found")
        return payload

    @router.get("/dashboard/api/v2/freshness-governance")
    async def dashboard_v2_freshness_governance(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return FreshnessGovernanceService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/risk-evidence-mesh")
    async def dashboard_v2_risk_evidence_mesh(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return RiskEvidenceMeshService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/risk-evidence-mesh/{evaluation_id}")
    async def dashboard_v2_risk_evidence_mesh_detail(evaluation_id: str) -> dict[str, object]:
        payload = RiskEvidenceMeshService().detail(evaluation_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Risk Evidence Mesh evaluation not found")
        return payload

    @router.get("/dashboard/api/v2/governance-calibration")
    async def dashboard_v2_governance_calibration(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return FreshnessGovernanceService().calibration_summary(limit=limit)

    @router.get("/dashboard/api/v2/truth-state")
    async def dashboard_v2_truth_state(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return TruthStateService().dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/truth-state/subject/{subject_id}")
    async def dashboard_v2_truth_state_subject(subject_id: str, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return TruthStateService().subject_detail(subject_id, limit=limit)

    @router.get("/dashboard/api/v2/truth-state/{truth_id}")
    async def dashboard_v2_truth_state_detail(truth_id: str) -> dict[str, object]:
        payload = TruthStateService().detail(truth_id)
        if payload.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail="Truth state record not found")
        return payload

    @router.get("/dashboard/api/v2/paper-intents")
    async def dashboard_v2_paper_intents(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PaperIntentGateService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/paper-intent-recovery")
    async def dashboard_v2_paper_intent_recovery(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PaperIntentGateService().get_recovery_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/paper-execution")
    async def dashboard_v2_paper_execution(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PaperExecutionService().get_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/paper-exits")
    async def dashboard_v2_paper_exits(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PaperExitLoopService().get_exits_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/paper-pnl")
    async def dashboard_v2_paper_pnl(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        return PaperExitLoopService().get_pnl_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/overnight/status")
    async def dashboard_v2_overnight_status(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return OvernightObservationStatusService().get_status(limit=limit)

    @router.post("/signals/market-binding/recover")
    async def signals_market_binding_recover(payload: SignalMarketBindingRecoveryRequest) -> dict[str, object]:
        return SignalMarketBindingRecoveryService().recover_market_bindings(
            limit=payload.limit,
            apply_safe_links=payload.apply_safe_links,
            create_suggestions=payload.create_suggestions,
            include_stale=payload.include_stale,
            include_dry_run=payload.include_dry_run,
        )

    @router.post("/thesis/profiles/build")
    async def thesis_profiles_build(payload: ThesisProfileBuildRequest) -> dict[str, object]:
        return ThesisProfileService().build_profiles(
            limit=payload.limit,
            include_incomplete=payload.include_incomplete,
            include_blocked=payload.include_blocked,
            write_profiles=payload.write_profiles,
        )

    @router.get("/thesis/profiles/recent")
    async def thesis_profiles_recent(
        limit: int = Query(default=50, ge=1, le=200),
        status: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object]:
        return ThesisProfileService().list_recent(limit=limit, status=status, market_id=market_id)

    @router.post("/risk/core/evaluate")
    async def risk_core_evaluate(payload: RiskCoreEvaluateRequest) -> dict[str, object]:
        return RiskCoreService().evaluate_risk(
            limit=payload.limit,
            include_blocked=payload.include_blocked,
            write_decisions=payload.write_decisions,
        )

    @router.post("/risk-evidence-mesh/evaluate")
    async def risk_evidence_mesh_evaluate(payload: RiskEvidenceMeshEvaluateRequest) -> dict[str, object]:
        return RiskEvidenceMeshService().evaluate_recent(
            limit=payload.limit,
            subject_type=payload.subject_type,
            dry_run=payload.dry_run,
        )

    @router.get("/risk/decisions/recent")
    async def risk_decisions_recent(
        limit: int = Query(default=50, ge=1, le=200),
        decision: str | None = None,
        market_id: str | None = None,
        thesis_id: str | None = None,
    ) -> dict[str, object]:
        return RiskCoreService().list_recent(limit=limit, decision=decision, market_id=market_id, thesis_id=thesis_id)

    @router.post("/exit/plans/build")
    async def exit_plans_build(payload: ExitPlanBuildRequest) -> dict[str, object]:
        return ExitFoundationService().build_exit_plans(
            limit=payload.limit,
            include_blocked=payload.include_blocked,
            write_plans=payload.write_plans,
        )

    @router.get("/exit/plans/recent")
    async def exit_plans_recent(
        limit: int = Query(default=50, ge=1, le=200),
        status: str | None = None,
        market_id: str | None = None,
        risk_decision_id: str | None = None,
    ) -> dict[str, object]:
        return ExitFoundationService().list_recent(
            limit=limit,
            status=status,
            market_id=market_id,
            risk_decision_id=risk_decision_id,
        )

    @router.post("/paper/eligibility/evaluate")
    async def paper_eligibility_evaluate(payload: PaperEligibilityEvaluateRequest) -> dict[str, object]:
        return PaperEligibilityService().evaluate_candidates(
            limit=payload.limit,
            include_blocked=payload.include_blocked,
            write_candidates=payload.write_candidates,
        )

    @router.get("/paper/eligibility/recent")
    async def paper_eligibility_recent(
        limit: int = Query(default=50, ge=1, le=200),
        status: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object]:
        return PaperEligibilityService().list_recent(limit=limit, status=status, market_id=market_id)

    @router.post("/paper/intents/build")
    async def paper_intents_build(payload: PaperIntentBuildRequest) -> dict[str, object]:
        return PaperIntentGateService().build_intents(
            limit=payload.limit,
            write_intents=payload.write_intents,
            write_no_trade=payload.write_no_trade,
        )

    @router.post("/paper/execution/run")
    async def paper_execution_run(payload: PaperExecutionRunRequest) -> dict[str, object]:
        return PaperExecutionService().run_execution(
            limit=payload.limit,
            cycle_id=payload.cycle_id,
            correlation_id=payload.correlation_id,
        )

    @router.post("/paper/exits/run")
    async def paper_exits_run(payload: PaperExitLoopRunRequest) -> dict[str, object]:
        return PaperExitLoopService().run_exit_loop(limit=payload.limit, correlation_id=payload.correlation_id)

    @router.post("/payout-odds/evaluate")
    async def payout_odds_evaluate(payload: PayoutOddsEvaluateRequest) -> dict[str, object]:
        return PayoutOddsService().evaluate_recent(
            limit=payload.limit,
            subject_type=payload.subject_type,
            dry_run=payload.dry_run,
        )

    @router.post("/exit-hold/evaluate")
    async def exit_hold_evaluate(payload: ExitHoldEvaluateRequest) -> dict[str, object]:
        return ExitHoldReasoningService().evaluate_recent(
            limit=payload.limit,
            subject_type=payload.subject_type,
            dry_run=payload.dry_run,
        )

    @router.post("/capital-efficiency/evaluate")
    async def capital_efficiency_evaluate(payload: CapitalEfficiencyEvaluateRequest) -> dict[str, object]:
        return CapitalEfficiencyService().evaluate_recent(
            limit=payload.limit,
            subject_type=payload.subject_type,
            dry_run=payload.dry_run,
        )

    @router.post("/trade-lifecycle/build")
    async def trade_lifecycle_build(payload: TradeLifecycleBuildRequest) -> dict[str, object]:
        return TradeLifecycleService().build_recent(
            limit=payload.limit,
            subject_type=payload.subject_type,
            dry_run=payload.dry_run,
        )

    @router.post("/lifecycle-governance/evaluate")
    async def lifecycle_governance_evaluate(payload: LifecycleGovernanceEvaluateRequest) -> dict[str, object]:
        return LifecycleGovernanceGateService().evaluate_recent(
            limit=payload.limit,
            subject_type=payload.subject_type,
            dry_run=payload.dry_run,
        )

    @router.post("/freshness-governance/evaluate")
    async def freshness_governance_evaluate(payload: FreshnessGovernanceEvaluateRequest) -> dict[str, object]:
        return FreshnessGovernanceService().evaluate_recent(limit=payload.limit, dry_run=payload.dry_run)

    @router.post("/truth-state/audit")
    async def truth_state_audit(payload: TruthStateAuditRequest) -> dict[str, object]:
        return TruthStateService().audit_current_db(limit=payload.limit, dry_run=payload.dry_run)

    @router.post("/paper/lineage/quarantine/run")
    async def paper_lineage_quarantine_run(payload: PaperLineageQuarantineRunRequest) -> dict[str, object]:
        return PaperLineageQuarantineService().run_quarantine(actor=payload.actor, limit=payload.limit)

    @router.get("/paper/lineage/quarantine/audit")
    async def paper_lineage_quarantine_audit(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        return PaperLineageQuarantineService().audit(limit=limit)

    @router.get("/paper/intents/recent")
    async def paper_intents_recent(
        limit: int = Query(default=50, ge=1, le=200),
        status: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object]:
        return PaperIntentGateService().list_recent(limit=limit, status=status, market_id=market_id)

    @router.post("/orderbook/snapshots/collect")
    async def orderbook_snapshots_collect(payload: OrderbookSnapshotCollectRequest) -> dict[str, object]:
        return OrderbookSnapshotService().collect_snapshots(
            limit=payload.limit,
            market_ids=payload.market_ids,
            source=payload.source,
        )

    @router.post("/trusted-orderbook/resolve")
    async def trusted_orderbook_resolve(payload: TrustedOrderbookResolveRequest) -> dict[str, object]:
        return TrustedOrderbookEvidenceService().resolve(
            cycle_id=payload.cycle_id,
            limit=payload.limit,
            refresh_orderbooks=payload.refresh_orderbooks,
        )

    @router.post("/polymarket-binding/recover")
    async def polymarket_binding_recover(payload: PolymarketBindingRecoveryRequest) -> dict[str, object]:
        return PolymarketIdentityBindingService().run_recovery(
            cycle_id=payload.cycle_id,
            limit=payload.limit,
            refresh_orderbooks=payload.refresh_orderbooks,
            apply_backfill=payload.apply_backfill,
        )

    @router.post("/polymarket-token-truth/recover")
    async def polymarket_token_truth_recover(payload: PolymarketTokenTruthRecoveryRequest) -> dict[str, object]:
        return PolymarketTokenTruthService().run_recovery(
            cycle_id=payload.cycle_id,
            candidate_limit=payload.candidate_limit,
            gamma_market_limit=payload.gamma_market_limit,
            verify_clob=payload.verify_clob,
            apply_backfill=payload.apply_backfill,
        )

    @router.post("/fresh-market-identity/recover")
    async def fresh_market_identity_recover(payload: FreshMarketIdentityRecoveryRequest) -> dict[str, object]:
        return FreshMarketIdentityGateService().run_recovery(
            cycle_id=payload.cycle_id,
            limit=payload.limit,
            dry_run=payload.dry_run,
            include_stale=payload.include_stale,
        )

    @router.post("/clob-token-book-verification/run")
    async def clob_token_book_verification_run(payload: ClobTokenBookVerificationRequest) -> dict[str, object]:
        return ClobTokenBookVerificationService().run_verification(
            cycle_id=payload.cycle_id,
            limit=payload.limit,
            seed_threshold=payload.seed_threshold,
            seed_limit=payload.seed_limit,
            verify_seeds=payload.verify_seeds,
        )

    @router.post("/live-orderbook-watcher/run")
    async def live_orderbook_watcher_run(payload: LiveOrderbookWatcherRunRequest) -> dict[str, object]:
        return LiveOrderbookWatcherService().run(
            cycle_id=payload.cycle_id,
            limit=payload.limit,
            dry_run=payload.dry_run,
            max_seconds=payload.max_seconds,
            include_priority=payload.include_priority,
        )

    @router.post("/open-position-watchdog/run")
    async def open_position_watchdog_run(payload: OpenPositionWatchdogRunRequest) -> dict[str, object]:
        return OpenPositionWatchdogService().run(
            cycle_id=payload.cycle_id,
            limit=payload.limit,
            dry_run=payload.dry_run,
            max_seconds=payload.max_seconds,
        )

    @router.post("/fresh-seed-paper-path/run")
    async def fresh_seed_paper_path_run(payload: FreshSeedPaperPathRunRequest) -> dict[str, object]:
        return FreshSeedPaperCandidateService().run(
            cycle_id=payload.cycle_id,
            limit=payload.limit,
            dry_run=payload.dry_run,
            max_seconds=payload.max_seconds,
        )

    @router.get("/orderbook/snapshots/recent")
    async def orderbook_snapshots_recent(
        limit: int = Query(default=50, ge=1, le=200),
        market_id: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        return OrderbookSnapshotService().list_recent(limit=limit, market_id=market_id, source=source, status=status)

    @router.post("/producers/runtime-evidence/run")
    async def producers_runtime_evidence_run(payload: RuntimeProducerEvidenceRunRequest) -> dict[str, object]:
        return RuntimeProducerEvidenceService().run_runtime_evidence_loop(
            limit=payload.limit,
            producer_names=payload.producer_names,
            dry_run=payload.dry_run,
            apply_evaluations=payload.apply_evaluations,
        )

    @router.post("/brain/runtime/run")
    async def brain_runtime_run(payload: RuntimeBrainRunRequest) -> dict[str, object]:
        return RuntimeBrainAdapterService().run_runtime_brain(
            limit=payload.limit,
            min_quality_score=payload.min_quality_score,
            write_outputs=payload.write_outputs,
        )

    @router.post("/coordinator/runtime/run")
    async def coordinator_runtime_run(payload: RuntimeCoordinatorRunRequest) -> dict[str, object]:
        return RuntimeCoordinatorDecisionService().run_runtime_coordinator(
            limit=payload.limit,
            min_brain_confidence=payload.min_brain_confidence,
            write_decisions=payload.write_decisions,
        )

    @router.get("/dashboard/api/v2/brain-outputs")
    async def dashboard_v2_brain_outputs(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return BrainOutputService().get_brain_output_summary(limit=limit)

    @router.get("/dashboard/api/v2/coordinator")
    async def dashboard_v2_coordinator(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return BrainCoordinatorService().get_coordinator_summary(limit=limit)

    @router.get("/dashboard/api/v2/impact-graph")
    async def dashboard_v2_impact_graph(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return ImpactGraphService().get_impact_graph_summary(limit=limit)

    @router.get("/dashboard/api/v2/mesh")
    async def dashboard_v2_mesh(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, object]:
        return MeshDashboardService().get_mesh_dashboard(limit=limit)

    @router.get("/dashboard/api/v2/mesh-dry-run")
    async def dashboard_v2_mesh_dry_run(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, object]:
        return MeshDryRunService().get_dry_run_summary(limit=limit)

    @router.get("/dashboard/api/v2/risk")
    async def dashboard_v2_risk(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("risk", limit=limit)

    @router.get("/dashboard/api/v2/engines")
    async def dashboard_v2_engines(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("engines", limit=limit)

    @router.get("/dashboard/api/v2/ai")
    async def dashboard_v2_ai(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("ai", limit=limit)

    @router.get("/dashboard/api/v2/no-trade")
    async def dashboard_v2_no_trade(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return PaperIntentGateService().get_no_trade_dashboard_summary(limit=limit)

    @router.get("/dashboard/api/v2/learning")
    async def dashboard_v2_learning(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("learning", limit=limit)

    @router.get("/dashboard/api/v2/memory")
    async def dashboard_v2_memory(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("memory", limit=limit)

    @router.get("/dashboard/api/v2/market")
    async def dashboard_v2_market(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("market", limit=limit)

    @router.get("/dashboard/api/v2/opportunities")
    async def dashboard_v2_opportunities(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("opportunities", limit=limit)

    @router.get("/dashboard/api/v2/capital")
    async def dashboard_v2_capital(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("capital", limit=limit)

    @router.get("/dashboard/api/v2/execution")
    async def dashboard_v2_execution(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("execution", limit=limit)

    @router.get("/dashboard/api/v2/exits")
    async def dashboard_v2_exits(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("exits", limit=limit)

    @router.get("/dashboard/api/v2/news")
    async def dashboard_v2_news(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("news", limit=limit)

    @router.get("/dashboard/api/v2/social")
    async def dashboard_v2_social(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("social", limit=limit)

    @router.get("/dashboard/api/v2/whales")
    async def dashboard_v2_whales(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("whales", limit=limit)

    @router.get("/dashboard/api/v2/live-flow")
    async def dashboard_v2_live_flow(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("live-flow", limit=limit)

    @router.get("/dashboard/api/v2/settings")
    async def dashboard_v2_settings(limit: int = Query(default=8, ge=1, le=50)) -> dict[str, object]:
        return DashboardV2QueryService().get_page("settings", limit=limit)

    @router.post("/telegram/command")
    async def telegram_command(payload: dict[str, object]) -> dict[str, object]:
        command = str(payload.get("command") or "")
        requested_by = payload.get("requested_by")
        response = TelegramCommandService().handle_command(
            command,
            requested_by=str(requested_by) if requested_by is not None else None,
        )
        return {
            "command": response.command,
            "supported": response.supported,
            "response_text": response.response_text,
            "sent": response.sent,
            "control_action_id": response.control_action_id,
        }

    @router.post("/telegram/webhook")
    async def telegram_webhook(
        payload: dict[str, object],
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")
        response = TelegramCommandService().handle_update(payload)
        return {
            "ok": True,
            "command": response.command,
            "supported": response.supported,
            "response_text": response.response_text,
            "control_action_id": response.control_action_id,
        }

    return router


def _render_control_center_placeholder_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>POLYBOT Control Center V1.5</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #05070d;
      --panel: #101827;
      --line: #2d3f5f;
      --text: #eef5ff;
      --muted: #a9b8d0;
      --accent: #20d6ff;
      --caution: #ffd166;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    main {
      width: min(960px, calc(100% - 32px));
      margin: 0 auto;
      padding: 64px 0;
    }
    .eyebrow {
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0;
      text-transform: uppercase;
    }
    h1 {
      margin: 10px 0 14px;
      font-size: 36px;
      line-height: 1.12;
      letter-spacing: 0;
    }
    p {
      max-width: 760px;
      color: var(--muted);
      font-size: 17px;
      line-height: 1.6;
    }
    .status {
      display: inline-block;
      margin: 18px 0 24px;
      padding: 8px 12px;
      border: 1px solid var(--caution);
      color: var(--caution);
      font-weight: 700;
    }
    section {
      margin-top: 28px;
      padding: 22px;
      border: 1px solid var(--line);
      background: var(--panel);
    }
    h2 {
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }
    ul {
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.7;
    }
    a {
      color: var(--accent);
    }
    code {
      color: var(--text);
    }
  </style>
</head>
<body>
  <main>
    <div class="eyebrow">POLYBOT Control Center V1.5</div>
    <h1>Reality-First + Decision X-Ray route reserved</h1>
    <div class="status">ROUTE_RESERVED / NOT_IMPLEMENTED</div>
    <p>
      The Control Center V1.5 route is reserved. The full UI is not implemented yet.
      No live data is displayed on this placeholder, no controls are active, and no trading, execution, paper, shadow, or live action is available from this page.
    </p>
    <p>
      The legacy dashboard remains available at <a href="/dashboard">/dashboard</a>
      until replacement is complete.
    </p>

    <section aria-labelledby="route-map-heading">
      <h2 id="route-map-heading">Route Map</h2>
      <ul>
        <li><code>/dashboard</code> - legacy current dashboard, preserved.</li>
        <li><code>/control-center</code> - future V1.5 shell, reserved only.</li>
        <li><code>/dashboard/api/v2/*</code> - existing truth APIs, not called by this placeholder.</li>
      </ul>
    </section>

    <section aria-labelledby="safety-boundary-heading">
      <h2 id="safety-boundary-heading">Safety Boundary</h2>
      <ul>
        <li>No runtime calls are made by this page.</li>
        <li>No database calls are made by this page.</li>
        <li>No mutating route is exposed by this page.</li>
      </ul>
    </section>
  </main>
</body>
</html>"""


def _render_dashboard_html(title: str, refresh_seconds: int) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #05070d;
      --panel: rgba(11, 18, 31, 0.86);
      --panel-strong: rgba(16, 27, 48, 0.96);
      --line: rgba(124, 165, 255, 0.18);
      --line-hot: rgba(45, 212, 255, 0.48);
      --text: #eef5ff;
      --muted: #91a4c7;
      --subtle: #5f718f;
      --cyan: #20d6ff;
      --blue: #4c8dff;
      --violet: #8c5cff;
      --good: #35e6a7;
      --warn: #ffd166;
      --danger: #ff4d6d;
      --shadow: rgba(0, 0, 0, 0.42);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Inter, "Segoe UI", "IBM Plex Sans", system-ui, sans-serif;
      background:
        radial-gradient(circle at 18% 6%, rgba(32, 214, 255, 0.14), transparent 26%),
        radial-gradient(circle at 82% 0%, rgba(140, 92, 255, 0.14), transparent 26%),
        linear-gradient(180deg, #05070d 0%, #07111f 45%, #04060b 100%);
      color: var(--text);
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
      background-size: 44px 44px;
      mask-image: linear-gradient(180deg, rgba(0,0,0,0.48), transparent 72%);
    }}
    .app {{
      display: grid;
      grid-template-columns: 248px minmax(0, 1fr);
      min-height: 100vh;
    }}
    aside {{
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 22px 14px;
      background: linear-gradient(180deg, rgba(8, 13, 24, 0.96), rgba(7, 10, 18, 0.92));
      border-right: 1px solid var(--line);
      box-shadow: 18px 0 50px rgba(0,0,0,0.28);
    }}
    .brand {{
      padding: 0 10px 18px;
      border-bottom: 1px solid var(--line);
      margin-bottom: 12px;
    }}
    .brand h1 {{
      margin: 0;
      font-size: 19px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .brand p {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    nav {{
      display: grid;
      gap: 5px;
    }}
    .nav-button {{
      width: 100%;
      border: 1px solid transparent;
      background: transparent;
      color: var(--muted);
      text-align: left;
      padding: 9px 10px;
      border-radius: 8px;
      cursor: pointer;
      font: inherit;
      font-size: 13px;
      letter-spacing: 0;
    }}
    .nav-button:hover,
    .nav-button.active {{
      color: var(--text);
      background: rgba(32, 214, 255, 0.08);
      border-color: rgba(32, 214, 255, 0.2);
    }}
    .workspace {{
      min-width: 0;
      padding: 20px 24px 36px;
      position: relative;
    }}
    .topbar {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .headline h2 {{
      margin: 0;
      font-size: 27px;
      letter-spacing: 0.01em;
    }}
    .headline p {{
      margin: 7px 0 0;
      color: var(--muted);
      max-width: 820px;
      line-height: 1.5;
    }}
    .pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid var(--line);
      background: rgba(12, 20, 35, 0.75);
      color: var(--muted);
      border-radius: 999px;
      padding: 6px 9px;
      font-size: 12px;
      white-space: nowrap;
    }}
    .dot {{
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: var(--subtle);
      box-shadow: 0 0 14px currentColor;
    }}
    .dot.ok {{ background: var(--good); color: var(--good); }}
    .dot.warn {{ background: var(--warn); color: var(--warn); }}
    .dot.bad {{ background: var(--danger); color: var(--danger); }}
    .pulse {{
      animation: pulse 1.8s ease-in-out infinite;
    }}
    @keyframes pulse {{
      0%, 100% {{ opacity: 0.55; transform: scale(0.88); }}
      50% {{ opacity: 1; transform: scale(1.12); }}
    }}
    .banner {{
      border: 1px solid rgba(255, 209, 102, 0.34);
      background: rgba(255, 209, 102, 0.08);
      color: #ffe3a1;
      padding: 10px 12px;
      border-radius: 8px;
      margin-bottom: 16px;
      display: none;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 12px;
    }}
    .panel {{
      grid-column: span 4;
      min-width: 0;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.045), rgba(255,255,255,0.015)),
        var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 22px 70px var(--shadow), inset 0 1px 0 rgba(255,255,255,0.04);
      padding: 14px;
      position: relative;
      overflow: hidden;
    }}
    .panel::after {{
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      border-top: 1px solid rgba(32,214,255,0.18);
    }}
    .panel.wide {{ grid-column: span 8; }}
    .panel.full {{ grid-column: 1 / -1; }}
    .panel h3 {{
      margin: 0 0 10px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--cyan);
    }}
    .metric {{
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 0;
      margin: 0;
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 5px;
    }}
    .bar {{
      height: 8px;
      border-radius: 999px;
      background: rgba(255,255,255,0.08);
      overflow: hidden;
      margin-top: 10px;
    }}
    .bar > span {{
      display: block;
      height: 100%;
      background: linear-gradient(90deg, var(--blue), var(--cyan));
    }}
    .flow {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 9px;
    }}
    .flow-node {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.035);
      border-radius: 8px;
      padding: 10px;
      min-height: 76px;
    }}
    .flow-node strong {{
      display: block;
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .feed {{
      display: grid;
      gap: 8px;
      max-height: 380px;
      overflow: auto;
      padding-right: 4px;
    }}
    .row {{
      border: 1px solid rgba(255,255,255,0.07);
      background: rgba(255,255,255,0.025);
      border-radius: 8px;
      padding: 9px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }}
    .json {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      color: #dce8ff;
      font-size: 12px;
      line-height: 1.5;
      max-height: 420px;
      overflow: auto;
    }}
    .control-lock {{
      display: grid;
      gap: 10px;
    }}
    input, textarea {{
      width: 100%;
      background: rgba(0,0,0,0.22);
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--text);
      padding: 10px;
      font: inherit;
    }}
    button.action {{
      border: 1px solid rgba(255, 77, 109, 0.4);
      background: rgba(255, 77, 109, 0.08);
      color: #ffd6de;
      border-radius: 8px;
      padding: 10px 12px;
      cursor: not-allowed;
      opacity: 0.74;
    }}
    .control-message {{
      color: var(--warn);
      min-height: 18px;
      font-size: 12px;
    }}
    .empty {{
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
      padding: 12px;
    }}
    @media (max-width: 980px) {{
      .app {{ grid-template-columns: 1fr; }}
      aside {{ position: relative; height: auto; }}
      nav {{ grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }}
      .topbar {{ display: block; }}
      .pills {{ justify-content: flex-start; margin-top: 12px; }}
      .panel, .panel.wide {{ grid-column: 1 / -1; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div class="brand">
        <h1>{title}</h1>
        <p>Upside open. Downside defined.</p>
      </div>
      <nav id="nav"></nav>
    </aside>
    <main class="workspace">
      <div class="topbar">
        <div class="headline">
          <h2 id="page-title">Overview</h2>
          <p id="page-subtitle">Runtime truth, capital posture, risk state, opportunity pressure, and refusal logic.</p>
        </div>
        <div class="pills">
          <span class="pill"><span id="status-dot" class="dot"></span><span id="status-pill">LOADING</span></span>
          <span class="pill" id="mode-pill">Mode: --</span>
          <span class="pill" id="updated-pill">Updated: --</span>
          <span class="pill">Refresh: {refresh_seconds}s</span>
        </div>
      </div>
      <div id="stale-banner" class="banner"></div>
      <section id="content" class="grid"></section>
    </main>
  </div>
  <script>
    const pages = [
      ['overview', 'Overview'],
      ['live-flow', 'Live Flow'],
      ['market', 'Markets'],
      ['opportunities', 'Opportunities'],
      ['engines', 'Engines'],
      ['risk', 'Risk'],
      ['capital', 'Capital'],
      ['execution', 'Positions'],
      ['exits', 'Exits'],
      ['news', 'News'],
      ['social', 'Social'],
      ['whales', 'Whales'],
      ['ai', 'AI Brain'],
      ['memory', 'Memory'],
      ['no-trade', 'No-Trade'],
      ['learning', 'Learning'],
      ['signals', 'Signals'],
      ['signal-lineage', 'Signal Lineage'],
      ['link-coverage', 'Link Coverage'],
      ['brain-outputs', 'Brain Outputs'],
      ['coordinator', 'Coordinator'],
      ['thesis', 'Thesis'],
      ['neurons', 'Neurons'],
      ['events', 'Events'],
      ['settings', 'Advanced Control']
    ];
    const requestedPage = new URLSearchParams(window.location.search).get('page');
    let currentPage = pages.some(([key]) => key === requestedPage) ? requestedPage : 'overview';
    const nav = document.getElementById('nav');
    const content = document.getElementById('content');
    const title = document.getElementById('page-title');
    const subtitle = document.getElementById('page-subtitle');
    const banner = document.getElementById('stale-banner');
    const statusPill = document.getElementById('status-pill');
    const statusDot = document.getElementById('status-dot');
    const modePill = document.getElementById('mode-pill');
    const updatedPill = document.getElementById('updated-pill');

    function setupNav() {{
      nav.innerHTML = pages.map(([key, label]) => `<button class="nav-button" data-page="${{key}}">${{label}}</button>`).join('');
      nav.querySelectorAll('button').forEach(button => {{
        button.addEventListener('click', () => {{
          currentPage = button.dataset.page;
          refreshDashboard();
        }});
      }});
    }}

    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, char => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
    }}

    function statusClass(status) {{
      const text = String(status || '').toUpperCase();
      if (['OK', 'HEALTHY', 'RUNNING'].includes(text)) return 'ok pulse';
      if (['ERROR', 'KILL', 'BLOCKED'].includes(text)) return 'bad';
      return 'warn';
    }}

    function metric(label, value, hint, span='') {{
      const rendered = value === null || value === undefined || value === '' ? 'INSUFFICIENT' : value;
      return `<article class="panel ${{span}}"><h3>${{esc(label)}}</h3><p class="metric">${{esc(rendered)}}</p><div class="label">${{esc(hint || '')}}</div></article>`;
    }}

    function jsonPanel(label, payload, span='wide') {{
      return `<article class="panel ${{span}}"><h3>${{esc(label)}}</h3><pre class="json">${{esc(JSON.stringify(payload, null, 2))}}</pre></article>`;
    }}

    function listPanel(label, rows, span='') {{
      const body = Array.isArray(rows) && rows.length
        ? `<div class="feed">${{rows.slice(0, 8).map(row => `<div class="row">${{esc(JSON.stringify(row))}}</div>`).join('')}}</div>`
        : '<div class="empty">NO_DATA</div>';
      return `<article class="panel ${{span}}"><h3>${{esc(label)}}</h3>${{body}}</article>`;
    }}

    function flowPanel(nodes) {{
      const body = (nodes || []).map(node => `
        <div class="flow-node">
          <strong>${{esc(node.label)}}</strong>
          <span class="pill"><span class="dot ${{statusClass(node.status)}}"></span>${{esc(node.status)}}</span>
          <div class="label">${{esc(node.latest_at || 'NO_DATA')}}</div>
        </div>`).join('');
      return `<article class="panel full"><h3>Neural Flow</h3><div class="flow">${{body}}</div></article>`;
    }}

    function controlsPanel(settings) {{
      const policy = settings?.advanced_controls || {{}};
      return `<article class="panel full">
        <h3>Advanced Control</h3>
        <div class="control-lock">
          <div class="row">State: LOCKED · Reason required · Confirmation required · Audit required</div>
          <input id="control-actor" placeholder="Actor">
          <textarea id="control-reason" rows="3" placeholder="Reason"></textarea>
          <input id="control-confirm" placeholder="Type CONFIRM">
          <button class="action" id="danger-action">Control unavailable from Dashboard V2</button>
          <div id="control-message" class="control-message"></div>
          <pre class="json">${{esc(JSON.stringify(policy, null, 2))}}</pre>
        </div>
      </article>`;
    }}

    function render(page, payload) {{
      const data = payload.data || {{}};
      const summary = data.summary || {{}};
      content.innerHTML = '';
      if (page === 'overview') {{
        content.innerHTML = [
          metric('System Mode', summary.system_mode, 'State Governor truth'),
          metric('Operational Status', summary.operational_status, 'Composite cockpit summary'),
          metric('Risk Status', summary.risk_status || summary.risk_governor_status, 'Risk Governor and Gate'),
          metric('Available Balance', summary.available_balance, 'Capital truth'),
          metric('Locked Capital', summary.locked_capital, 'Allocated or unavailable'),
          metric('PnL Today', summary.pnl_today, 'Paper/live source if available'),
          metric('Open Positions', summary.open_positions, 'Canonical internal truth'),
          metric('Kill Switch', summary.kill_switch ? 'ACTIVE' : 'CLEAR', 'Safety state'),
          metric('AI Cost', summary.ai_cost, 'AI budget ledger'),
          metric('Live Certified', summary.live_certified ? 'YES' : 'NO', 'Live boundary'),
          listPanel('Top Opportunities', summary.top_opportunities, 'wide'),
          jsonPanel('Risk / Capital / Refusal Truth', {{risk: data.risk, capital: data.capital, no_trade: data.no_trade}}, 'full')
        ].join('');
      }} else if (page === 'live-flow') {{
        content.innerHTML = flowPanel(data.nodes || []);
      }} else if (page === 'settings') {{
        content.innerHTML = [
          controlsPanel(data.settings || data),
          jsonPanel('Settings Truth', data, 'full')
        ].join('');
        const action = document.getElementById('danger-action');
        action?.addEventListener('click', () => {{
          const reason = document.getElementById('control-reason')?.value.trim();
          const confirm = document.getElementById('control-confirm')?.value.trim();
          const message = document.getElementById('control-message');
          if (!reason || confirm !== 'CONFIRM') {{
            message.textContent = 'Blocked: unlock, reason, and explicit confirmation are required.';
            return;
          }}
          message.textContent = 'Blocked: no safe Dashboard V2 control endpoint is available in this phase.';
        }});
      }} else {{
        const module = Object.values(data)[0] || data;
        const rows = Object.entries(module).filter(([, value]) => Array.isArray(value) && value.length);
        content.innerHTML = [
          metric('Status', payload.status, payload.stale ? payload.stale_reason : 'Fresh enough for operator view'),
          metric('Data Confidence', payload.data_confidence, 'Computed from source freshness and errors'),
          metric('Stale', payload.stale ? 'YES' : 'NO', payload.stale_reason || 'No stale warning'),
          ...rows.slice(0, 3).map(([key, value]) => listPanel(key, value)),
          jsonPanel('Source Truth', data, 'full')
        ].join('');
      }}
    }}

    async function refreshDashboard() {{
      for (const button of nav.querySelectorAll('button')) {{
        button.classList.toggle('active', button.dataset.page === currentPage);
      }}
      const label = pages.find(([key]) => key === currentPage)?.[1] || currentPage;
      title.textContent = label;
      subtitle.textContent = currentPage === 'settings'
        ? 'Controls are locked unless the backend exposes a safe audited endpoint.'
        : 'DB-backed truth with stale and insufficient-data states surfaced directly.';
      const response = await fetch(`/dashboard/api/v2/${{currentPage}}?limit=8`);
      const payload = await response.json();
      statusPill.textContent = payload.status;
      statusDot.className = `dot ${{statusClass(payload.status)}}`;
      modePill.textContent = `Mode: ${{payload.data?.summary?.system_mode || payload.data?.runtime?.current_mode || '--'}}`;
      updatedPill.textContent = `Updated: ${{payload.updated_at || '--'}}`;
      banner.style.display = payload.stale ? 'block' : 'none';
      banner.textContent = payload.stale ? `STALE / DEGRADED: ${{payload.stale_reason || 'source did not report current data'}}` : '';
      render(currentPage, payload);
    }}
    setupNav();
    refreshDashboard();
    setInterval(refreshDashboard, {refresh_seconds * 1000});
  </script>
</body>
</html>"""
