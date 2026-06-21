from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.mesh_blockers import MeshBlocker, MeshBlockerReport
from app.runtime.health_truth import HealthTruthService
from app.services.dry_run_provenance import DryRunProvenanceService
from app.services.exit_foundation import ExitFoundationService
from app.services.lineage_coverage import LineageCoverageService
from app.services.link_coverage import LinkCoverageService
from app.services.orderbook_snapshots import OrderbookSnapshotService
from app.services.paper_eligibility import PaperEligibilityService
from app.services.paper_intents import PaperIntentGateService
from app.services.producer_health import ProducerHealthService
from app.services.risk_core import RiskCoreService
from app.services.signal_processing import SignalProcessingService
from app.services.signal_quality import SignalQualityService
from app.services.thesis_profiles import ThesisProfileService


class MeshBlockersService:
    """Read-only Paper readiness blocker analysis from DB/runtime truth."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def get_mesh_blockers(self, *, limit: int = 20) -> dict[str, Any]:
        try:
            truth = self._load_truth(limit=limit)
            return build_mesh_blocker_report(truth).to_api_dict()
        except Exception as exc:
            now = datetime.now(UTC)
            blocker = MeshBlocker(
                code="MESH_BLOCKER_ANALYSIS_ERROR",
                active=True,
                severity="CRITICAL",
                category="DASHBOARD",
                reason="Mesh blocker analysis failed before all readiness truth could be collected.",
                evidence={"error_type": type(exc).__name__, "error": str(exc)},
                source="mesh_blockers",
                recommended_next_step="Fix the blocker analyzer error before making any Paper readiness claim.",
                blocks_paper=True,
            )
            return MeshBlockerReport(
                mock_data=False,
                paper_ready=False,
                overall_status="UNKNOWN",
                blocked_by=[blocker.code],
                blockers=[blocker],
                info=[],
                counts=_count_blockers([blocker], []),
                last_updated=now,
                analysis_status="ERROR",
            ).to_api_dict()

    def _load_truth(self, *, limit: int) -> dict[str, Any]:
        runtime = self._runtime_truth()
        signal_quality = _safe_summary(lambda: SignalQualityService(connection_factory=self._factory).get_signal_quality_summary(limit=limit))
        signal_processing = _safe_summary(lambda: SignalProcessingService(connection_factory=self._factory).get_signal_processing_summary(limit=limit))
        link_coverage = _safe_summary(lambda: LinkCoverageService(connection_factory=self._factory).get_link_coverage_summary(limit=limit))
        lineage_coverage = _safe_summary(lambda: LineageCoverageService(connection_factory=self._factory).get_lineage_coverage_summary(limit=limit))
        dry_run_provenance = _safe_summary(lambda: DryRunProvenanceService(connection_factory=self._factory).get_summary(limit=limit))
        producer_health = _safe_summary(lambda: ProducerHealthService(connection_factory=self._factory).get_producer_health_summary(limit=limit))
        thesis = _safe_summary(lambda: ThesisProfileService(connection_factory=self._factory).get_dashboard_summary(limit=limit))
        risk_core = _safe_summary(lambda: RiskCoreService(connection_factory=self._factory).get_dashboard_summary(limit=limit))
        exit_foundation = _safe_summary(lambda: ExitFoundationService(connection_factory=self._factory).get_dashboard_summary(limit=limit))
        paper_eligibility = _safe_summary(lambda: PaperEligibilityService(connection_factory=self._factory).get_dashboard_summary(limit=limit))
        paper_intents = _safe_summary(lambda: PaperIntentGateService(connection_factory=self._factory).get_dashboard_summary(limit=limit))
        no_trade = _safe_summary(lambda: PaperIntentGateService(connection_factory=self._factory).get_no_trade_dashboard_summary(limit=limit))
        orderbook = _safe_summary(lambda: OrderbookSnapshotService(connection_factory=self._factory).get_dashboard_summary(limit=limit))

        counts = {
            "orderbook_snapshots": self._count_table("orderbook_snapshots"),
            "paper_orders": self._count_table("paper_orders"),
            "shadow_orders": self._count_table("shadow_orders"),
            "live_orders": self._count_table("live_orders"),
            "order_intents": self._count_first_existing(["order_intents"]),
            "execution_allowed_true": self._count_where("coordinator_decisions", "execution_allowed = true"),
            "risk_core_evidence": self._count_first_existing(["risk_decisions", "mesh_risk_core_evidence", "risk_core_certifications", "risk_core_evidence"]),
            "exit_foundation_evidence": _int(exit_foundation.get("total_exit_plans")),
            "paper_eligibility_evidence": _int(paper_eligibility.get("total_candidates")),
            "paper_intents": _int(paper_intents.get("total_paper_intents")),
            "no_trade_log": _int(no_trade.get("total_no_trade_records")),
        }
        tables = {
            "orderbook_snapshots_exists": self._table_exists("orderbook_snapshots"),
            "order_intents_exists": self._table_exists("order_intents"),
        }
        return {
            "runtime": runtime,
            "signal_quality": signal_quality,
            "signal_processing": signal_processing,
            "link_coverage": link_coverage,
            "lineage_coverage": lineage_coverage,
            "dry_run_provenance": dry_run_provenance,
            "producer_health": producer_health,
            "thesis": thesis,
            "risk_core": risk_core,
            "exit_foundation": exit_foundation,
            "paper_eligibility": paper_eligibility,
            "paper_intents": paper_intents,
            "no_trade": no_trade,
            "orderbook": orderbook,
            "counts": counts,
            "tables": tables,
        }

    def _runtime_truth(self) -> dict[str, Any]:
        health = HealthTruthService(connection_factory=self._factory).get_health_truth()
        persisted_mode = health.get("current_mode")
        env_mode = os.getenv("POLYBOT_RUNTIME_MODE")
        kill_env = _str_bool(os.getenv("LIVE_KILL_SWITCH"))
        kill_persisted = health.get("kill_switch_active")
        live_enabled = _str_bool(os.getenv("LIVE_TRADING_ENABLED"))
        return {
            "current_mode": persisted_mode,
            "persisted_mode": persisted_mode,
            "env_mode": env_mode,
            "live_enabled": bool(live_enabled),
            "kill_switch_env": kill_env,
            "kill_switch_persisted": kill_persisted,
            "mode_mismatch": bool(env_mode and persisted_mode and env_mode != persisted_mode),
            "kill_switch_mismatch": kill_env is not None and kill_persisted is not None and kill_env != bool(kill_persisted),
            "runtime_health": health.get("overall_status"),
            "permissions": health.get("permissions") or {},
        }

    def _count_table(self, table: str) -> int:
        if not self._factory.enabled:
            return 0
        try:
            with self._factory.connect() as conn:
                if not _table_exists(conn, table):
                    return 0
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                return int(row["count"] or 0)
        except Exception:
            return 0

    def _count_where(self, table: str, where: str) -> int:
        if not self._factory.enabled:
            return 0
        try:
            with self._factory.connect() as conn:
                if not _table_exists(conn, table):
                    return 0
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()
                return int(row["count"] or 0)
        except Exception:
            return 0

    def _count_first_existing(self, tables: list[str]) -> int:
        for table in tables:
            count = self._count_table(table)
            if count > 0:
                return count
        return 0

    def _table_exists(self, table: str) -> bool:
        if not self._factory.enabled:
            return False
        try:
            with self._factory.connect() as conn:
                return _table_exists(conn, table)
        except Exception:
            return False


def build_mesh_blocker_report(truth: dict[str, Any]) -> MeshBlockerReport:
    now = datetime.now(UTC)
    active_blockers: list[MeshBlocker] = []
    info: list[MeshBlocker] = []

    runtime = truth.get("runtime") or {}
    signal_quality = truth.get("signal_quality") or {}
    signal_processing = truth.get("signal_processing") or {}
    link_coverage = truth.get("link_coverage") or {}
    lineage_coverage = truth.get("lineage_coverage") or {}
    provenance = truth.get("dry_run_provenance") or {}
    producer_health = truth.get("producer_health") or {}
    thesis = truth.get("thesis") or {}
    risk_core = truth.get("risk_core") or {}
    exit_foundation = truth.get("exit_foundation") or {}
    paper_eligibility = truth.get("paper_eligibility") or {}
    paper_intents = truth.get("paper_intents") or {}
    no_trade = truth.get("no_trade") or {}
    orderbook = truth.get("orderbook") or {}
    counts = truth.get("counts") or {}
    tables = truth.get("tables") or {}

    def add(
        code: str,
        active: bool,
        severity: str,
        category: str,
        reason: str,
        evidence: dict[str, Any],
        source: str,
        recommended_next_step: str,
        *,
        blocks_paper: bool = True,
    ) -> None:
        item = MeshBlocker(
            code=code,
            active=active,
            severity=severity,
            category=category,
            reason=reason,
            evidence=_json_safe(evidence),
            source=source,
            recommended_next_step=recommended_next_step,
            blocks_paper=blocks_paper,
        )
        if not item.active:
            return
        if item.blocks_paper:
            active_blockers.append(item)
        else:
            info.append(item)

    orderbook_count = _int(counts.get("orderbook_snapshots"))
    fresh_orderbooks = _int(orderbook.get("fresh_snapshots"))
    stale_orderbooks = _int(orderbook.get("stale_snapshots"))
    orderbook_coverage = _float(orderbook.get("orderbook_coverage_ratio"))
    add(
        "ORDERBOOK_SNAPSHOTS_MISSING",
        orderbook_count == 0 or fresh_orderbooks == 0,
        "CRITICAL",
        "DATA",
        "Fresh orderbook snapshots are absent, so Paper readiness has no liquidity or spread evidence.",
        {
            "orderbook_snapshots_exists": bool(tables.get("orderbook_snapshots_exists")),
            "orderbook_snapshots": orderbook_count,
            "fresh_snapshots": fresh_orderbooks,
            "latest_collected_at": orderbook.get("latest_collected_at"),
        },
        "orderbook_snapshots",
        "Implement or restore non-executing orderbook snapshot coverage before Paper certification.",
    )
    add(
        "ORDERBOOK_SNAPSHOTS_STALE",
        orderbook_count > 0 and fresh_orderbooks == 0 and stale_orderbooks > 0,
        "HIGH",
        "DATA",
        "Orderbook snapshots exist but are stale, so Paper readiness cannot trust spread or liquidity evidence.",
        {"stale_snapshots": stale_orderbooks, "freshness_window_seconds": orderbook.get("freshness_window_seconds")},
        "orderbook_snapshots",
        "Refresh orderbook snapshots before Paper eligibility checks.",
    )
    add(
        "ORDERBOOK_COVERAGE_LOW",
        fresh_orderbooks > 0 and orderbook_coverage < 0.5,
        "MEDIUM",
        "DATA",
        "Fresh orderbook coverage exists but covers too few active tradable markets.",
        {
            "orderbook_coverage_ratio": orderbook_coverage,
            "markets_with_orderbook": orderbook.get("markets_with_orderbook", 0),
            "active_tradable_markets": orderbook.get("active_tradable_markets", 0),
        },
        "orderbook_snapshots",
        "Expand orderbook snapshot coverage after the first fresh snapshot path is stable.",
    )

    processing_total = _int(signal_processing.get("total"))
    unprocessed = _int(signal_processing.get("unprocessed_count"))
    add(
        "SIGNAL_PROCESSING_INCOMPLETE",
        processing_total == 0 or unprocessed > 0,
        "HIGH",
        "SIGNALS",
        "Signals are not fully represented in processing state, so downstream readiness cannot trust the flow.",
        {"total": processing_total, "unprocessed_count": unprocessed, "by_state": signal_processing.get("by_state", [])},
        "signal_processing",
        "Run and harden signal processing state until all Signals have deterministic state.",
    )

    paper_quality = _int(signal_quality.get("can_feed_paper"))
    paper_processing = _int(signal_processing.get("paper_eligible_informational_count"))
    add(
        "SIGNAL_QUALITY_GATE_BLOCKED",
        paper_quality == 0 or paper_processing == 0 or _int(signal_processing.get("rejected_count")) > 0,
        "HIGH",
        "SIGNALS",
        "Signal quality gates do not currently provide Paper-eligible evidence.",
        {
            "signal_quality_can_feed_paper": paper_quality,
            "processing_paper_eligible_informational": paper_processing,
            "rejected_count": _int(signal_processing.get("rejected_count")),
        },
        "signal_quality",
        "Improve Signal quality inputs and processing gate coverage without treating eligibility as trade approval.",
    )

    link_ratio = _float(link_coverage.get("link_coverage_ratio"))
    add(
        "SIGNAL_LINKING_TOO_LOW",
        link_ratio < 0.8,
        "HIGH",
        "LINKAGE",
        "Signal-to-market link coverage is below the Paper-readiness threshold.",
        {
            "link_coverage_ratio": link_ratio,
            "linked_signals": _int(link_coverage.get("linked_signals")),
            "unlinked_signals": _int(link_coverage.get("unlinked_signals")),
        },
        "link_coverage",
        "Improve evidence-backed link coverage; do not force weak links.",
    )

    stale_count = _int(signal_processing.get("stale_count"))
    add(
        "SIGNALS_STALE_HIGH",
        stale_count > 0,
        "HIGH",
        "SIGNALS",
        "Stale Signals are present in the processing state and block Paper evidence.",
        {"stale_count": stale_count, "total": processing_total},
        "signal_processing",
        "Improve freshness and source cadence before Paper evidence collection.",
    )

    lineage_ratio = _float(lineage_coverage.get("lineage_coverage_ratio"))
    unbound = _int(lineage_coverage.get("unbound_signals"))
    add(
        "SIGNAL_LINEAGE_COVERAGE_LOW",
        lineage_ratio < 0.8 or unbound > 0,
        "HIGH",
        "LINEAGE",
        "Signal lineage coverage is incomplete, so Signals cannot fully explain origin and trust.",
        {"lineage_coverage_ratio": lineage_ratio, "unbound_signals": unbound, "missing_lineage_fields": lineage_coverage.get("missing_lineage_fields", [])},
        "lineage_coverage",
        "Close producer, source, correlation, and payload lineage gaps.",
    )

    brain_runtime = _int(provenance.get("brain_outputs_runtime"))
    brain_dry = _int(provenance.get("brain_outputs_dry_run"))
    coord_runtime = _int(provenance.get("coordinator_decisions_runtime"))
    coord_dry = _int(provenance.get("coordinator_decisions_dry_run"))
    add(
        "BRAIN_OUTPUTS_DRY_RUN_ONLY",
        brain_dry > 0 and brain_runtime == 0,
        "CRITICAL",
        "BRAIN",
        "Brain Outputs exist only as dry-run outputs.",
        {"brain_outputs_total": _int(provenance.get("brain_outputs_total")), "brain_outputs_runtime": brain_runtime, "brain_outputs_dry_run": brain_dry},
        "dry_run_provenance",
        "Implement runtime brain producer adapters, non-executing and quality-gated.",
    )
    add(
        "COORDINATOR_DECISIONS_DRY_RUN_ONLY",
        coord_dry > 0 and coord_runtime == 0,
        "CRITICAL",
        "COORDINATOR",
        "Coordinator Decisions exist only as dry-run decisions.",
        {"coordinator_decisions_total": _int(provenance.get("coordinator_decisions_total")), "coordinator_decisions_runtime": coord_runtime, "coordinator_decisions_dry_run": coord_dry},
        "dry_run_provenance",
        "Wire runtime coordinator decisions after brain producer adapters are producing non-executing runtime outputs.",
    )
    add(
        "NO_RUNTIME_BRAIN_OUTPUTS",
        brain_runtime == 0,
        "CRITICAL",
        "BRAIN",
        "No runtime Brain Outputs are available for Paper readiness evidence.",
        {"brain_outputs_runtime": brain_runtime},
        "dry_run_provenance",
        "Create runtime Brain Outputs from quality-gated Signals without enabling execution.",
    )
    add(
        "NO_RUNTIME_COORDINATOR_DECISIONS",
        coord_runtime == 0,
        "CRITICAL",
        "COORDINATOR",
        "No runtime Coordinator Decisions are available for Paper readiness evidence.",
        {"coordinator_decisions_runtime": coord_runtime},
        "dry_run_provenance",
        "Create runtime Coordinator Decisions from runtime Brain Outputs while keeping execution disabled.",
    )
    blocked_from_paper = _int(provenance.get("blocked_from_paper_count"))
    add(
        "DRY_RUN_EVIDENCE_BLOCKED_FROM_PAPER",
        blocked_from_paper > 0 or brain_dry > 0 or coord_dry > 0,
        "CRITICAL",
        "PROVENANCE",
        "Dry-run evidence exists and is explicitly excluded from production Paper readiness.",
        {"blocked_from_paper_count": blocked_from_paper, "brain_outputs_dry_run": brain_dry, "coordinator_decisions_dry_run": coord_dry},
        "dry_run_provenance",
        "Preserve dry-run observability, but build separate runtime evidence.",
    )

    thesis_total = _int(thesis.get("total_thesis_profiles"))
    add(
        "NO_THESIS_PROFILES",
        thesis_total == 0,
        "HIGH",
        "DATA",
        "No runtime Thesis Profiles exist, so future Paper candidates lack required thesis contracts.",
        {"total_thesis_profiles": thesis_total, "runtime_thesis_profiles": _int(thesis.get("runtime_thesis_profiles"))},
        "thesis",
        "Create real runtime thesis profiles from non-executing Coordinator evidence.",
    )
    add(
        "THESIS_PROFILES_INCOMPLETE",
        thesis_total > 0 and _int(thesis.get("complete_thesis_profiles")) == 0,
        "HIGH",
        "DATA",
        "Thesis Profiles exist but none are complete enough for downstream Paper eligibility.",
        {
            "total_thesis_profiles": thesis_total,
            "complete_thesis_profiles": _int(thesis.get("complete_thesis_profiles")),
            "incomplete_thesis_profiles": _int(thesis.get("incomplete_thesis_profiles")),
            "blocked_thesis_profiles": _int(thesis.get("blocked_thesis_profiles")),
        },
        "thesis",
        "Resolve missing market, orderbook, binding, lineage, and provenance evidence before Paper eligibility.",
    )
    add(
        "THESIS_PROFILES_MISSING_MARKET",
        _int(thesis.get("missing_market_count")) > 0,
        "HIGH",
        "DATA",
        "Some Thesis Profiles are missing market_id and cannot become complete.",
        {"missing_market_count": _int(thesis.get("missing_market_count"))},
        "thesis",
        "Recover market binding for runtime Signals and Coordinator Decisions before Paper eligibility.",
    )
    add(
        "THESIS_PROFILES_MISSING_ORDERBOOK",
        _int(thesis.get("missing_orderbook_count")) > 0,
        "HIGH",
        "DATA",
        "Some Thesis Profiles are missing fresh orderbook evidence.",
        {"missing_orderbook_count": _int(thesis.get("missing_orderbook_count"))},
        "thesis",
        "Refresh orderbook snapshots for thesis markets before Paper eligibility.",
    )

    add(
        "NO_RISK_CORE",
        _int(risk_core.get("total_risk_decisions")) == 0,
        "CRITICAL",
        "RISK",
        "No current thesis-derived Risk Core decisions exist.",
        {
            "risk_core_evidence": _int(counts.get("risk_core_evidence")),
            "total_risk_decisions": _int(risk_core.get("total_risk_decisions")),
        },
        "risk_core",
        "Run Risk Core evaluation against runtime thesis profiles before Paper eligibility.",
    )
    add(
        "RISK_DECISIONS_ALL_BLOCKED",
        _int(risk_core.get("total_risk_decisions")) > 0
        and _int(risk_core.get("blocked_count")) == _int(risk_core.get("total_risk_decisions")),
        "HIGH",
        "RISK",
        "Risk Core decisions exist, but every evaluated thesis is blocked.",
        {
            "total_risk_decisions": _int(risk_core.get("total_risk_decisions")),
            "blocked_count": _int(risk_core.get("blocked_count")),
            "top_risk_blockers": risk_core.get("top_risk_blockers", []),
        },
        "risk_core",
        "Resolve thesis, market binding, orderbook, confidence, and downstream Exit gaps before Paper eligibility.",
    )
    add(
        "RISK_CORE_APPROVALS_BLOCKED_BY_EXIT",
        _int(risk_core.get("risk_approved_count")) > 0 and _int(counts.get("exit_foundation_evidence")) == 0,
        "HIGH",
        "RISK",
        "Risk-layer approvals exist, but Exit Foundation is missing so Paper eligibility remains blocked.",
        {
            "risk_approved_count": _int(risk_core.get("risk_approved_count")),
            "exit_foundation_evidence": _int(counts.get("exit_foundation_evidence")),
        },
        "risk_core",
        "Implement Exit Foundation before any risk-approved thesis can become a Paper candidate.",
    )
    add(
        "RISK_CORE_MISSING_DATA",
        _int(risk_core.get("missing_data_risk_count")) > 0,
        "HIGH",
        "RISK",
        "Risk Core found missing market, orderbook, binding, lineage, or provenance evidence.",
        {
            "missing_data_risk_count": _int(risk_core.get("missing_data_risk_count")),
            "top_risk_blockers": risk_core.get("top_risk_blockers", []),
        },
        "risk_core",
        "Close missing evidence before expecting Risk Core approvals.",
    )
    add(
        "NO_EXIT_FOUNDATION",
        _int(exit_foundation.get("total_exit_plans")) == 0,
        "CRITICAL",
        "EXIT",
        "No current Exit Foundation plans exist.",
        {"total_exit_plans": _int(exit_foundation.get("total_exit_plans"))},
        "exit_foundation",
        "Implement Exit Foundation before any Paper position can be opened.",
    )
    add(
        "EXIT_PLANS_ALL_BLOCKED",
        _int(exit_foundation.get("total_exit_plans")) > 0
        and _int(exit_foundation.get("blocked_exit_plans")) == _int(exit_foundation.get("total_exit_plans")),
        "HIGH",
        "EXIT",
        "Exit Foundation plans exist, but every plan is blocked.",
        {
            "total_exit_plans": _int(exit_foundation.get("total_exit_plans")),
            "blocked_exit_plans": _int(exit_foundation.get("blocked_exit_plans")),
            "top_exit_blockers": exit_foundation.get("top_exit_blockers", []),
        },
        "exit_foundation",
        "Resolve Risk, market, orderbook, and side evidence before Paper eligibility.",
    )
    add(
        "EXIT_PLANS_INCOMPLETE",
        _int(exit_foundation.get("incomplete_exit_plans")) > 0,
        "HIGH",
        "EXIT",
        "Some Exit Foundation plans are incomplete and cannot protect future entries.",
        {
            "incomplete_exit_plans": _int(exit_foundation.get("incomplete_exit_plans")),
            "missing_exit_evidence_summary": exit_foundation.get("missing_exit_evidence_summary", []),
        },
        "exit_foundation",
        "Close missing exit evidence before Paper eligibility.",
    )
    add(
        "EXIT_MISSING_ORDERBOOK",
        _int(exit_foundation.get("missing_orderbook_count")) > 0,
        "HIGH",
        "EXIT",
        "Some Exit Foundation plans are missing fresh orderbook evidence.",
        {"missing_orderbook_count": _int(exit_foundation.get("missing_orderbook_count"))},
        "exit_foundation",
        "Refresh or bind orderbook evidence for candidate markets before Paper eligibility.",
    )
    add(
        "EXIT_MISSING_RISK_APPROVAL",
        _int(exit_foundation.get("missing_risk_approval_count")) > 0,
        "HIGH",
        "EXIT",
        "Some Exit Foundation plans are blocked because Risk Core did not approve the thesis.",
        {"missing_risk_approval_count": _int(exit_foundation.get("missing_risk_approval_count"))},
        "exit_foundation",
        "Resolve Risk Core blockers before Paper eligibility.",
    )
    add(
        "NO_PAPER_ELIGIBLE_SIGNALS",
        _int(paper_eligibility.get("eligible_count")) == 0,
        "CRITICAL",
        "SIGNALS",
        "No fully evidenced Paper Eligibility candidates currently qualify for future Paper intent creation.",
        {
            "eligible_count": _int(paper_eligibility.get("eligible_count")),
            "total_candidates": _int(paper_eligibility.get("total_candidates")),
            "signal_quality_can_feed_paper": paper_quality,
            "processing_paper_eligible_informational": paper_processing,
        },
        "paper_eligibility",
        "Resolve exit, risk, thesis, binding, orderbook, lineage, and provenance blockers before Paper intents.",
    )
    add(
        "PAPER_ELIGIBILITY_ALL_BLOCKED",
        _int(paper_eligibility.get("total_candidates")) > 0
        and _int(paper_eligibility.get("blocked_count")) == _int(paper_eligibility.get("total_candidates")),
        "HIGH",
        "PAPER_ELIGIBILITY",
        "Paper Eligibility candidates exist, but every candidate is blocked.",
        {
            "total_candidates": _int(paper_eligibility.get("total_candidates")),
            "blocked_count": _int(paper_eligibility.get("blocked_count")),
            "top_eligibility_blockers": paper_eligibility.get("top_eligibility_blockers", []),
        },
        "paper_eligibility",
        "Resolve top eligibility blockers before any Paper Intent Gate phase.",
    )
    add(
        "PAPER_ELIGIBILITY_MISSING_EXIT",
        _int(paper_eligibility.get("missing_exit_plan_count")) > 0,
        "HIGH",
        "PAPER_ELIGIBILITY",
        "Some Paper Eligibility candidates are missing a ready exit plan.",
        {"missing_exit_plan_count": _int(paper_eligibility.get("missing_exit_plan_count"))},
        "paper_eligibility",
        "Build and complete Exit Foundation plans before eligibility can pass.",
    )
    add(
        "PAPER_ELIGIBILITY_MISSING_RISK",
        _int(paper_eligibility.get("missing_risk_decision_count")) > 0,
        "HIGH",
        "PAPER_ELIGIBILITY",
        "Some Paper Eligibility candidates are missing Risk Core decisions.",
        {"missing_risk_decision_count": _int(paper_eligibility.get("missing_risk_decision_count"))},
        "paper_eligibility",
        "Run Risk Core and keep blocked risk decisions ineligible.",
    )
    add(
        "PAPER_ELIGIBILITY_MISSING_BINDING",
        _int(paper_eligibility.get("missing_binding_count")) > 0,
        "HIGH",
        "PAPER_ELIGIBILITY",
        "Some Paper Eligibility candidates lack trusted signal-market binding.",
        {"missing_binding_count": _int(paper_eligibility.get("missing_binding_count"))},
        "paper_eligibility",
        "Recover only evidence-backed signal-market links before eligibility can pass.",
    )
    add(
        "PAPER_ELIGIBILITY_MISSING_ORDERBOOK",
        _int(paper_eligibility.get("missing_orderbook_count")) > 0,
        "HIGH",
        "PAPER_ELIGIBILITY",
        "Some Paper Eligibility candidates lack fresh orderbook evidence.",
        {"missing_orderbook_count": _int(paper_eligibility.get("missing_orderbook_count"))},
        "paper_eligibility",
        "Refresh orderbook snapshots and keep stale evidence blocked.",
    )
    add(
        "NO_PAPER_INTENTS",
        _int(paper_intents.get("total_paper_intents")) == 0,
        "HIGH",
        "PAPER_INTENT",
        "No non-executing Paper Intent records exist yet.",
        {
            "total_paper_intents": _int(paper_intents.get("total_paper_intents")),
            "eligible_candidates": _int(paper_intents.get("eligible_candidates")),
        },
        "paper_intent_gate",
        "Run Paper Intent Gate after eligibility candidates exist; create intents only for truly eligible candidates.",
    )
    add(
        "PAPER_INTENTS_BLOCKED_BY_ELIGIBILITY",
        _int(paper_eligibility.get("eligible_count")) == 0,
        "HIGH",
        "PAPER_INTENT",
        "Paper Intent creation is blocked because there are no eligible Paper Eligibility candidates.",
        {
            "eligible_count": _int(paper_eligibility.get("eligible_count")),
            "blocked_count": _int(paper_eligibility.get("blocked_count")),
            "total_candidates": _int(paper_eligibility.get("total_candidates")),
        },
        "paper_intent_gate",
        "Resolve Paper Eligibility blockers; blocked candidates must become No-Trade records, not intents.",
    )
    add(
        "NO_TRADE_LEDGER_MISSING",
        _int(paper_eligibility.get("blocked_count")) > 0 and _int(no_trade.get("total_no_trade_records")) == 0,
        "HIGH",
        "NO_TRADE",
        "Blocked Paper Eligibility candidates exist but have not yet been ledgered as NO_TRADE records.",
        {
            "blocked_candidates": _int(paper_eligibility.get("blocked_count")),
            "total_no_trade_records": _int(no_trade.get("total_no_trade_records")),
        },
        "no_trade_ledger",
        "Run the Paper Intent Gate with No-Trade writing enabled so blocked candidates are durably accounted for.",
    )
    add(
        "UNACCOUNTED_CANDIDATES",
        _int(paper_intents.get("unaccounted_candidates")) > 0 or _int(no_trade.get("unaccounted_candidates")) > 0,
        "CRITICAL",
        "NO_TRADE",
        "Some Paper Eligibility candidates lack both a Paper Intent and a No-Trade ledger record.",
        {
            "paper_intent_unaccounted_candidates": _int(paper_intents.get("unaccounted_candidates")),
            "no_trade_unaccounted_candidates": _int(no_trade.get("unaccounted_candidates")),
        },
        "paper_intent_gate",
        "Re-run Paper Intent Gate; every candidate must produce exactly one safe outcome.",
    )
    add(
        "PRODUCER_HEALTH_DEGRADED",
        _int(producer_health.get("degraded_neurons") and len(producer_health.get("degraded_neurons") or [])) > 0,
        "HIGH",
        "SIGNALS",
        "One or more producers are degraded by stale output, incomplete lineage, or weak quality.",
        {
            "degraded_neurons": producer_health.get("degraded_neurons", []),
            "overall_status": producer_health.get("overall_status"),
        },
        "producer_health",
        "Harden producer quality, lineage, and freshness before Paper evidence collection.",
    )
    add(
        "EXPECTED_NEURONS_SILENT",
        _int(producer_health.get("silent_expected_neurons") and len(producer_health.get("silent_expected_neurons") or [])) > 0,
        "HIGH",
        "SIGNALS",
        "Expected registered neurons are silent and have no observed producer evidence.",
        {"silent_expected_neurons": producer_health.get("silent_expected_neurons", [])},
        "producer_health",
        "Investigate expected silent producers before runtime brain production.",
    )
    add(
        "PRODUCERS_DRY_RUN_ONLY",
        _int(producer_health.get("dry_run_only_producers")) > 0,
        "HIGH",
        "PROVENANCE",
        "Some producers have only dry-run-derived evidence.",
        {
            "dry_run_only_producers": producer_health.get("dry_run_only_producers", 0),
            "dry_run_only_neurons": producer_health.get("dry_run_only_neurons", []),
        },
        "producer_health",
        "Build runtime producer evidence separately from dry-run observability.",
    )
    add(
        "PRODUCER_RUNTIME_EVIDENCE_MISSING",
        _int(producer_health.get("runtime_active_producers")) == 0,
        "HIGH",
        "SIGNALS",
        "No producers are currently classified as runtime-active.",
        {"runtime_active_producers": producer_health.get("runtime_active_producers", 0)},
        "producer_health",
        "Create non-executing runtime producer evidence after producer health gaps are understood.",
    )
    add(
        "ENV_PERSISTED_MODE_MISMATCH",
        bool(runtime.get("mode_mismatch")),
        "MEDIUM",
        "RUNTIME",
        "Environment runtime mode differs from persisted runtime mode.",
        {"env_mode": runtime.get("env_mode"), "persisted_mode": runtime.get("persisted_mode")},
        "runtime",
        "Resolve runtime mode mismatch before Paper certification.",
    )
    add(
        "ENV_PERSISTED_KILL_SWITCH_MISMATCH",
        bool(runtime.get("kill_switch_mismatch")),
        "MEDIUM",
        "RUNTIME",
        "Environment kill switch differs from persisted kill switch state.",
        {"kill_switch_env": runtime.get("kill_switch_env"), "kill_switch_persisted": runtime.get("kill_switch_persisted")},
        "runtime",
        "Resolve kill switch truth mismatch before Paper certification.",
    )
    add(
        "EXECUTION_NOT_ALLOWED",
        not bool((runtime.get("permissions") or {}).get("can_run_paper_engine")),
        "HIGH",
        "EXECUTION",
        "The runtime permissions do not allow Paper execution.",
        {"permissions": runtime.get("permissions") or {}},
        "runtime",
        "Keep execution disabled until all Paper evidence gates are certified.",
    )
    add(
        "ORDER_INTENTS_ABSENT",
        _int(counts.get("order_intents")) == 0,
        "INFO",
        "EXECUTION",
        "No order intents exist, which is expected before Paper readiness.",
        {"order_intents_exists": bool(truth.get("tables", {}).get("order_intents_exists")), "order_intents": _int(counts.get("order_intents"))},
        "execution_safety",
        "Keep order intents absent until a certified Paper phase explicitly introduces them.",
        blocks_paper=False,
    )
    add(
        "PAPER_ORDERS_ZERO",
        _int(counts.get("paper_orders")) == 0,
        "INFO",
        "EXECUTION",
        "Paper orders are zero, confirming this phase did not enable Paper trading.",
        {"paper_orders": _int(counts.get("paper_orders"))},
        "execution_safety",
        "Continue to keep Paper orders at zero until Paper Full System certification.",
        blocks_paper=False,
    )
    add(
        "LIVE_DISABLED",
        not bool(runtime.get("live_enabled")),
        "INFO",
        "EXECUTION",
        "Live trading is disabled.",
        {"live_enabled": bool(runtime.get("live_enabled"))},
        "runtime",
        "Keep live trading disabled until a future explicitly certified live phase.",
        blocks_paper=False,
    )

    blocked_by = sorted(item.code for item in active_blockers if item.active and item.blocks_paper)
    overall_status = _overall_status(active_blockers)
    return MeshBlockerReport(
        mock_data=False,
        paper_ready=False,
        overall_status=overall_status,
        blocked_by=blocked_by,
        blockers=sorted(active_blockers, key=lambda item: (_severity_rank(item.severity), item.code)),
        info=sorted(info, key=lambda item: item.code),
        counts=_count_blockers(active_blockers, info),
        last_updated=now,
        analysis_status="OK",
    )


def _overall_status(blockers: list[MeshBlocker]) -> str:
    if any(item.active and item.blocks_paper and item.severity in {"CRITICAL", "HIGH"} for item in blockers):
        return "BLOCKED"
    if any(item.active and item.blocks_paper for item in blockers):
        return "DEGRADED"
    return "READY"


def _count_blockers(blockers: list[MeshBlocker], info: list[MeshBlocker]) -> dict[str, int]:
    all_items = [*blockers, *info]
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "active_blockers": 0}
    for item in all_items:
        if not item.active:
            continue
        key = str(item.severity).lower()
        if key in counts:
            counts[key] += 1
        if item.blocks_paper:
            counts["active_blockers"] += 1
    return counts


def _severity_rank(severity: str) -> int:
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(str(severity).upper(), 5)


def _safe_summary(loader: Any) -> dict[str, Any]:
    try:
        payload = loader()
        if isinstance(payload, dict):
            return payload
        return {}
    except Exception as exc:
        return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}", "mock_data": False}


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _str_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


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
