from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FullMeshOrganRegistration:
    neuron_name: str
    neuron_type: str
    service_module: str
    questions: tuple[str, ...]
    required_inputs: tuple[str, ...] = ("candidate_id", "market_id", "side", "token_id")
    optional_inputs: tuple[str, ...] = ("condition_id", "correlation_id", "event_id")
    candidate_scoped: bool = True
    market_level_only: bool = False
    directional_evidence: bool = False
    can_write_data_only: bool = False
    safe_for_pre_paper_inquiry: bool = True
    availability: str = "AVAILABLE"
    passive_only: bool = False
    exemption_reason: str | None = None
    adapter_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "neuron_name": self.neuron_name,
            "neuron_type": self.neuron_type,
            "service_module": self.service_module,
            "questions": list(self.questions),
            "required_inputs": list(self.required_inputs),
            "optional_inputs": list(self.optional_inputs),
            "candidate_scoped": self.candidate_scoped,
            "market_level_only": self.market_level_only,
            "directional_evidence": self.directional_evidence,
            "can_write_data_only": self.can_write_data_only,
            "safe_for_pre_paper_inquiry": self.safe_for_pre_paper_inquiry,
            "availability": self.availability,
            "passive_only": self.passive_only,
            "exemption_reason": self.exemption_reason,
            "adapter_name": self.adapter_name,
            "metadata": dict(self.metadata),
        }


DECISION_CRITICAL_ORGANS = {
    "candidate",
    "candidate_event_correlation",
    "trusted_orderbook",
    "candidate_price_path",
    "liquidity",
    "source_backed_edge",
    "risk",
    "exit",
    "capital",
    "same_market_guard",
    "lifecycle",
    "coordinator",
    "paper_actionability",
    "pre_paper_safety",
}


FULL_MESH_ORGANS: tuple[FullMeshOrganRegistration, ...] = (
    FullMeshOrganRegistration("candidate", "CANDIDATE", "app.services.paper_eligibility", ("Who is the candidate?", "Is candidate identity complete?"), directional_evidence=False, adapter_name="candidate"),
    FullMeshOrganRegistration("candidate_event_correlation", "CANDIDATE", "app.control_center.candidate_event_correlation", ("Is this event linked to the candidate?",), adapter_name="candidate_event_correlation"),
    FullMeshOrganRegistration("trusted_orderbook", "ORDERBOOK", "app.services.trusted_orderbook", ("What is the candidate-specific entry price?", "Is the orderbook fresh?"), directional_evidence=False, adapter_name="orderbook"),
    FullMeshOrganRegistration("candidate_price_path", "ORDERBOOK", "app.control_center.orderbook_price_readiness", ("Is candidate-specific price ready?",), adapter_name="candidate_price_path"),
    FullMeshOrganRegistration("liquidity", "LIQUIDITY", "app.market_neuron.liquidity_analyzer", ("Can we enter and exit safely?", "What is depth and spread?"), directional_evidence=False, adapter_name="liquidity"),
    FullMeshOrganRegistration("market_movement", "MARKET", "app.market_neuron.technical_signal_builder", ("Did price move recently?", "Is movement aligned with side?"), directional_evidence=True, adapter_name="market_movement", metadata={"tables": ["market_technical_signals", "orderbook_signals"]}),
    FullMeshOrganRegistration("news", "NEWS", "app.news_neuron.service", ("Is there fresh market-linked news?", "Does it support YES or NO?"), candidate_scoped=False, market_level_only=True, directional_evidence=True, adapter_name="news", metadata={"tables": ["news_impact_scores", "news_market_links"], "config_keys": ["NEWS_API_KEY", "NEWS_RSS_FEEDS", "CRYPTOPANIC_API_KEY"]}),
    FullMeshOrganRegistration("whale", "WHALE", "app.whale_neuron.service", ("Is there meaningful whale flow?", "Is it aligned with side?"), candidate_scoped=False, market_level_only=True, directional_evidence=True, adapter_name="whale", metadata={"tables": ["whale_events", "whale_market_scores"], "config_keys": ["POLYMARKET_CLOB_API_KEY", "POLYMARKET_CLOB_SECRET", "POLYMARKET_CLOB_PASSPHRASE"]}),
    FullMeshOrganRegistration("social", "SOCIAL", "app.social_neuron.service", ("Is social pressure relevant?", "Does social evidence support this side?"), candidate_scoped=False, market_level_only=True, directional_evidence=True, adapter_name="social", metadata={"tables": ["social_market_links", "social_hype_scores"], "config_keys": ["X_BEARER_TOKEN", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "TELEGRAM_API_ID", "TELEGRAM_API_HASH"]}),
    FullMeshOrganRegistration("cross_market", "CROSS_MARKET", "future.cross_market", ("Is there a fresh cross-market discrepancy?",), candidate_scoped=False, market_level_only=True, directional_evidence=True, availability="UNAVAILABLE", adapter_name="cross_market", metadata={"tables": ["external_market_prices", "cross_market_discrepancies", "external_odds"]}),
    FullMeshOrganRegistration("market_memory", "MEMORY", "app.market_memory", ("Has this setup worked before?",), candidate_scoped=False, market_level_only=True, directional_evidence=False, adapter_name="market_memory", metadata={"tables": ["market_memory_v2", "market_family_memory", "no_trade_memory"]}),
    FullMeshOrganRegistration("signal_quality", "SIGNAL", "app.services.signal_quality", ("Is a linked source signal high quality enough to feed brains?",), candidate_scoped=False, market_level_only=True, directional_evidence=True, adapter_name="signal_quality", metadata={"tables": ["neuron_signals", "neuron_signal_bindings", "signal_quality_evaluations"]}),
    FullMeshOrganRegistration("signal_processing", "SIGNAL", "app.services.signal_processing", ("Is a linked source signal processed and directional?",), candidate_scoped=False, market_level_only=True, directional_evidence=True, adapter_name="signal_processing", metadata={"tables": ["neuron_signals", "neuron_signal_bindings"]}),
    FullMeshOrganRegistration("payout", "PAYOUT", "app.services.payout_odds", ("Does payout/odds evidence support an economic thesis?",), directional_evidence=True, adapter_name="payout", metadata={"tables": ["payout_odds_evaluations", "payout_odds_sources"]}),
    FullMeshOrganRegistration("source_backed_edge", "OTHER", "app.services.source_backed_edge_engine", ("Is the edge source-backed and risk-usable?",), directional_evidence=True, adapter_name="source_backed_edge"),
    FullMeshOrganRegistration("risk", "RISK", "app.services.risk_evidence_mesh", ("Is the edge usable by risk?", "What blocks risk?"), adapter_name="risk"),
    FullMeshOrganRegistration("exit", "EXIT", "app.services.exit_foundation", ("Is there a valid candidate-specific exit plan?",), adapter_name="exit"),
    FullMeshOrganRegistration("capital", "CAPITAL", "app.services.paper_capital", ("Is capital available without mutation?",), adapter_name="capital"),
    FullMeshOrganRegistration("same_market_guard", "RISK", "app.services.same_market_side_guard", ("Is there duplicate same-market exposure?",), adapter_name="same_market_guard"),
    FullMeshOrganRegistration("lifecycle", "LIFECYCLE", "app.services.lifecycle_governance", ("Are lifecycle gates satisfied?",), adapter_name="lifecycle"),
    FullMeshOrganRegistration("coordinator", "COORDINATOR", "app.events.consumers.orderbook_mesh_consumer", ("What final Mesh decision was reached?",), adapter_name="coordinator"),
    FullMeshOrganRegistration("ai_reasoner", "AI", "app.services.ai_edge_reasoner", ("What is the thesis and counter-thesis?",), directional_evidence=False, availability="PASSIVE", passive_only=True, adapter_name="ai_reasoner"),
    FullMeshOrganRegistration("paper_actionability", "ACTIONABILITY", "app.control_center.paper_actionability", ("Could this become small paper if enabled?",), adapter_name="paper_actionability"),
    FullMeshOrganRegistration("pre_paper_safety", "SAFETY", "app.control_center.pre_paper_safety", ("Can Phase 10 start safely?",), adapter_name="pre_paper_safety"),
    FullMeshOrganRegistration("runtime_supervisor", "OTHER", "app.control_center.runtime_supervisor", ("Is runtime collection alive?",), candidate_scoped=False, directional_evidence=False, adapter_name="runtime_supervisor"),
    FullMeshOrganRegistration("state_governor", "SAFETY", "app.runtime.state_governor", ("What runtime modes are allowed?",), candidate_scoped=False, directional_evidence=False, adapter_name="state_governor"),
)


EXPLICITLY_EXEMPT_ORGANS: dict[str, str] = {
    "paper_execution": "Execution is deliberately outside pre-paper inquiry and must remain blocked unless Phase 10 enables Paper Simulation.",
    "live_execution": "Live execution is forbidden for this phase.",
}


def full_mesh_registry() -> list[FullMeshOrganRegistration]:
    return list(FULL_MESH_ORGANS)


def registry_by_name() -> dict[str, FullMeshOrganRegistration]:
    return {item.neuron_name: item for item in FULL_MESH_ORGANS}


def validate_decision_critical_coverage() -> dict[str, Any]:
    registered = set(registry_by_name())
    missing = sorted(DECISION_CRITICAL_ORGANS.difference(registered).difference(EXPLICITLY_EXEMPT_ORGANS))
    return {
        "status": "OK" if not missing else "MISSING_CORE_ORGANS",
        "required": sorted(DECISION_CRITICAL_ORGANS),
        "registered": sorted(registered),
        "exempt": EXPLICITLY_EXEMPT_ORGANS,
        "missing": missing,
    }
