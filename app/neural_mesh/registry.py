from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


NeuronStatus = Literal["ACTIVE", "PARTIAL", "DISABLED", "MISSING", "DEGRADED", "STALE", "ERROR"]

VALID_NEURON_STATUSES = {"ACTIVE", "PARTIAL", "DISABLED", "MISSING", "DEGRADED", "STALE", "ERROR"}


class NeuronRegistryEntry(BaseModel):
    neuron_name: str
    display_name: str
    category: str
    description: str
    expected_signal_types: list[str] = Field(default_factory=list)
    producer_source: str | None = None
    is_required_for_paper: bool = False
    is_required_for_live: bool = False
    default_status: NeuronStatus = "MISSING"
    enabled: bool = True
    owner_component: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("neuron_name")
    @classmethod
    def normalize_neuron_name(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("neuron_name is required")
        return normalized

    @field_validator("display_name", "category", "description")
    @classmethod
    def require_text(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("registry field is required")
        return normalized

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class NeuronHealth(BaseModel):
    neuron_name: str
    runtime_status: NeuronStatus
    health_status: NeuronStatus
    last_signal_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    stale_after_seconds: int = Field(default=3600, ge=0)
    is_stale: bool = False
    expected_to_emit: bool = True
    enabled: bool = True
    source_status_name: str | None = None
    signal_count_1h: int = Field(default=0, ge=0)
    signal_count_24h: int = Field(default=0, ge=0)
    error_count_24h: int = Field(default=0, ge=0)
    updated_at: datetime | None = None

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class NeuronRuntimeStats(BaseModel):
    neuron_name: str
    total_signals: int = Field(default=0, ge=0)
    signals_1m: int = Field(default=0, ge=0)
    signals_5m: int = Field(default=0, ge=0)
    signals_1h: int = Field(default=0, ge=0)
    signals_24h: int = Field(default=0, ge=0)
    last_signal_at: datetime | None = None
    active_market_count: int = Field(default=0, ge=0)
    stale_signal_count: int = Field(default=0, ge=0)
    unprocessed_signal_count: int = Field(default=0, ge=0)
    latest_status: str | None = None
    updated_at: datetime | None = None

    def to_api_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


DEFAULT_NEURONS: tuple[NeuronRegistryEntry, ...] = (
    NeuronRegistryEntry(neuron_name="market", display_name="Market Neuron", category="market", description="Market discovery and price/source availability observations.", expected_signal_types=["source_status_observed"], producer_source="source_status", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="source_status"),
    NeuronRegistryEntry(neuron_name="orderbook", display_name="Orderbook Neuron", category="market", description="Orderbook, spread, and depth source observations.", expected_signal_types=["source_status_observed"], producer_source="source_status", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="source_status"),
    NeuronRegistryEntry(neuron_name="liquidity", display_name="Liquidity Neuron", category="market", description="Liquidity observations and future liquidity signals.", producer_source="future_connector", is_required_for_paper=True, is_required_for_live=True, default_status="MISSING", owner_component="market_neuron"),
    NeuronRegistryEntry(neuron_name="rules", display_name="Rules Neuron", category="intelligence", description="Rules, wording, and compliance observations.", expected_signal_types=["rules_resolution_status_observed"], producer_source="rules_resolution", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="rules_resolution_truth"),
    NeuronRegistryEntry(neuron_name="resolution", display_name="Resolution Neuron", category="intelligence", description="Resolution source clarity observations.", expected_signal_types=["rules_resolution_status_observed"], producer_source="rules_resolution", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="rules_resolution_truth"),
    NeuronRegistryEntry(neuron_name="news", display_name="News Neuron", category="intelligence", description="External news catalyst observations.", expected_signal_types=["source_status_observed"], producer_source="source_status", is_required_for_live=True, default_status="DISABLED", enabled=False, owner_component="news_provider"),
    NeuronRegistryEntry(neuron_name="social", display_name="Social / Hype Neuron", category="intelligence", description="Social attention and hype observations.", expected_signal_types=["source_status_observed"], producer_source="source_status", is_required_for_live=True, default_status="DISABLED", enabled=False, owner_component="reddit_or_social_provider"),
    NeuronRegistryEntry(neuron_name="whale", display_name="Whale Neuron", category="intelligence", description="Whale and activity observations.", expected_signal_types=["source_status_observed"], producer_source="source_status", is_required_for_live=True, default_status="PARTIAL", owner_component="polymarket_activity_readonly"),
    NeuronRegistryEntry(neuron_name="time", display_name="Time Neuron", category="market", description="Time-to-close and timing context observations.", producer_source="future_connector", is_required_for_paper=True, is_required_for_live=True, default_status="MISSING", owner_component="market_neuron"),
    NeuronRegistryEntry(neuron_name="fees", display_name="Fees Neuron", category="market", description="Fees, rewards, and transaction-cost observations.", producer_source="future_connector", is_required_for_paper=True, is_required_for_live=True, default_status="MISSING", owner_component="market_neuron"),
    NeuronRegistryEntry(neuron_name="ai", display_name="AI Neuron", category="ai", description="Local/cloud AI availability and interpretation observations.", expected_signal_types=["source_status_observed"], producer_source="source_status", is_required_for_live=True, default_status="PARTIAL", owner_component="ollama_local_model"),
    NeuronRegistryEntry(neuron_name="risk", display_name="Risk Neuron", category="risk", description="Risk gate and governor observations.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="risk_gate_governor"),
    NeuronRegistryEntry(neuron_name="capital", display_name="Capital Neuron", category="capital", description="Capital availability and allocation observations.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="capital_allocator"),
    NeuronRegistryEntry(neuron_name="position", display_name="Position Neuron", category="execution", description="Position state observations.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="MISSING", owner_component="execution_cortex_v2"),
    NeuronRegistryEntry(neuron_name="exit", display_name="Exit Neuron", category="exit", description="Exit-plan and exit-state observations.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="exit_cortex_v2"),
    NeuronRegistryEntry(neuron_name="source", display_name="Source Status Neuron", category="system", description="Source availability rollup observations.", expected_signal_types=["source_status_observed"], producer_source="source_status", is_required_for_live=True, default_status="PARTIAL", owner_component="source_status"),
    NeuronRegistryEntry(neuron_name="execution", display_name="Execution Neuron", category="execution", description="Execution-cortex observational status.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="execution_cortex_v2"),
    NeuronRegistryEntry(neuron_name="no_trade", display_name="No-Trade Neuron", category="system", description="No-trade intelligence observational status.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="no_trade_intelligence"),
    NeuronRegistryEntry(neuron_name="opportunity", display_name="Opportunity Neuron", category="system", description="Opportunity cortex observational status.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="opportunity_cortex"),
    NeuronRegistryEntry(neuron_name="strategy", display_name="Strategy Neuron", category="system", description="Strategy-router observational status.", producer_source="manual", is_required_for_paper=True, is_required_for_live=True, default_status="PARTIAL", owner_component="strategy_router"),
    NeuronRegistryEntry(neuron_name="memory", display_name="Memory Neuron", category="memory", description="Market-memory observational status.", producer_source="manual", is_required_for_live=True, default_status="PARTIAL", owner_component="market_memory"),
    NeuronRegistryEntry(neuron_name="learning", display_name="Learning Neuron", category="memory", description="Feedback and learning loop observational status.", producer_source="manual", is_required_for_live=True, default_status="PARTIAL", owner_component="feedback_learning_loop"),
)


REQUIRED_NEURON_NAMES = {
    "market",
    "orderbook",
    "liquidity",
    "rules",
    "resolution",
    "news",
    "social",
    "whale",
    "time",
    "fees",
    "ai",
    "risk",
    "capital",
    "position",
    "exit",
}


def registry_entry_from_row(row: dict[str, Any]) -> NeuronRegistryEntry:
    data = dict(row)
    data["expected_signal_types"] = data.get("expected_signal_types") or []
    return NeuronRegistryEntry(**data)
