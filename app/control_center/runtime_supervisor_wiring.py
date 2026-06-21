from __future__ import annotations

from app.control_center.runtime_supervisor import RuntimeSupervisorService
from app.runtime.state_governor import StateGovernor
from app.services.live_orderbook_watcher import LiveOrderbookWatcherService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.source_refresh_orchestrator import SourceRefreshOrchestrator
from app.services.trusted_orderbook import TrustedOrderbookEvidenceService


def build_runtime_supervisor(*, governor: StateGovernor | None = None) -> RuntimeSupervisorService:
    """Build the canonical DATA_ONLY runtime supervisor wiring used by SYSTEM ON."""

    resolved_governor = governor or StateGovernor()
    return RuntimeSupervisorService(
        governor=resolved_governor,
        candidate_producer=PaperEligibilityService(),
        candidate_orderbook_refresher=TrustedOrderbookEvidenceService(),
        orderbook_refresher=LiveOrderbookWatcherService(),
        source_refresh_orchestrator=SourceRefreshOrchestrator(governor=resolved_governor),
    )
