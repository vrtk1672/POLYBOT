from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.market_memory.service import MarketMemoryService
from app.market_neuron.service import MarketNeuronService
from app.news_neuron.service import NewsNeuronService
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.capital_efficiency import CapitalEfficiencyService
from app.services.ai_mesh_intelligence import AIMarketIntelligenceMeshOrgan, AIMeshConfig
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.market_universe_memory import MarketUniverseMemoryService
from app.services.multi_trigger_candidate_generation import MultiTriggerProactiveCandidateGeneratorService
from app.services.payout_odds import PayoutOddsService
from app.services.proactive_candidate_generation import ProactiveCandidateGenerationService
from app.services.proactive_seed_mesh_adapter import ProactiveSeedDataOnlyMeshAdapter
from app.services.proactive_seed_mesh_inquiry import ProactiveSeedMeshInquiryService
from app.services.research_priority_watchlist import ResearchPriorityWatchlistService
from app.services.risk_evidence_mesh import RiskEvidenceMeshService
from app.services.source_event_memory import SourceEventMemoryService
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService
from app.services.trade_thesis_engine import TradeThesisEngine
from app.services.trade_lifecycle import TradeLifecycleService
from app.whale_neuron.service import WhaleNeuronService


SOURCE_REFRESH_STATES = {
    "FRESH",
    "REFRESHING_CURRENTLY",
    "REFRESHING_NO_NEW_DATA",
    "REFRESHING_BUT_NOT_CANDIDATE_LINKED",
    "REFRESHING_BUT_NOT_DIRECTIONAL",
    "STALE_BY_TTL",
    "NO_REFRESH_PRODUCER",
    "PRODUCER_NOT_IN_SUPERVISOR",
    "MISSING_CONFIG",
    "NO_CONNECTOR",
    "FAILED_WITH_ERROR",
    "DISABLED",
    "KNOWN_NOT_IMPLEMENTED",
    "UNKNOWN",
}


@dataclass(frozen=True)
class SourceRefreshRegistration:
    source_name: str
    source_type: str
    refresh_mode: str
    ttl_seconds: int
    refresh_interval_seconds: int
    candidate_scoped_supported: bool = False
    market_level_supported: bool = True
    directional_supported: bool = False
    safe_to_refresh_data_only: bool = True
    required_config_keys: tuple[str, ...] = ()
    table_name: str | None = None
    timestamp_column: str | None = None


@dataclass
class SourceRefreshContract:
    source_name: str
    source_type: str
    enabled: bool
    refresh_mode: str
    candidate_scoped_supported: bool
    market_level_supported: bool
    directional_supported: bool
    last_refresh_attempt_at: datetime | None = None
    last_successful_refresh_at: datetime | None = None
    latest_data_at: datetime | None = None
    latest_error_at: datetime | None = None
    latest_error_code: str | None = None
    refresh_interval_seconds: int = 0
    ttl_seconds: int = 0
    freshness_seconds: int | None = None
    refresh_state: str = "UNKNOWN"
    rows_total: int = 0
    rows_last_24h: int = 0
    rows_last_1h: int = 0
    rows_last_15m: int = 0
    candidate_linked_rows: int = 0
    directional_rows: int = 0
    safe_to_refresh_data_only: bool = True
    required_config_keys: list[str] = field(default_factory=list)
    missing_config_keys: list[str] = field(default_factory=list)
    blocker_code: str | None = None
    required_to_pass: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        state = self.refresh_state if self.refresh_state in SOURCE_REFRESH_STATES else "UNKNOWN"
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "enabled": self.enabled,
            "refresh_mode": self.refresh_mode,
            "candidate_scoped_supported": self.candidate_scoped_supported,
            "market_level_supported": self.market_level_supported,
            "directional_supported": self.directional_supported,
            "last_refresh_attempt_at": self.last_refresh_attempt_at,
            "last_successful_refresh_at": self.last_successful_refresh_at,
            "latest_data_at": self.latest_data_at,
            "latest_error_at": self.latest_error_at,
            "latest_error_code": self.latest_error_code,
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "ttl_seconds": self.ttl_seconds,
            "freshness_seconds": self.freshness_seconds,
            "refresh_state": state,
            "rows_total": self.rows_total,
            "rows_last_24h": self.rows_last_24h,
            "rows_last_1h": self.rows_last_1h,
            "rows_last_15m": self.rows_last_15m,
            "candidate_linked_rows": self.candidate_linked_rows,
            "directional_rows": self.directional_rows,
            "safe_to_refresh_data_only": self.safe_to_refresh_data_only,
            "required_config_keys": list(self.required_config_keys),
            "missing_config_keys": list(self.missing_config_keys),
            "blocker_code": self.blocker_code,
            "required_to_pass": list(self.required_to_pass),
            "metadata_json": dict(self.metadata),
        }

    def to_api_dict(self) -> dict[str, Any]:
        row = self.to_row()
        for key in ("last_refresh_attempt_at", "last_successful_refresh_at", "latest_data_at", "latest_error_at"):
            value = row.get(key)
            row[key] = value.isoformat() if hasattr(value, "isoformat") else value
        row["metadata"] = row.pop("metadata_json")
        return row


SOURCE_REFRESH_REGISTRY: tuple[SourceRefreshRegistration, ...] = (
    SourceRefreshRegistration("clob_orderbook", "ORDERBOOK", "SUPERVISOR_CYCLE", 120, 60, True, True, False, table_name="orderbook_snapshots", timestamp_column="collected_at"),
    SourceRefreshRegistration("candidate_price_path", "ORDERBOOK", "CANDIDATE_TRIGGERED", 120, 60, True, False, False, table_name="orderbook_snapshots", timestamp_column="collected_at"),
    SourceRefreshRegistration("liquidity", "LIQUIDITY", "DERIVED", 900, 300, True, True, False, table_name="liquidity_signals", timestamp_column="ts"),
    SourceRefreshRegistration("orderbook_signals", "ORDERBOOK_SIGNAL", "DERIVED", 900, 300, True, True, True, table_name="orderbook_signals", timestamp_column="ts"),
    SourceRefreshRegistration("market_movement", "MARKET_MOVEMENT", "DERIVED", 900, 300, True, True, True, table_name="market_technical_signals", timestamp_column="ts"),
    SourceRefreshRegistration("market_technical_signals", "TECHNICAL", "DERIVED", 900, 300, True, True, True, table_name="market_technical_signals", timestamp_column="ts"),
    SourceRefreshRegistration("market_memory_v2", "MEMORY", "DERIVED", 86400, 3600, False, True, False, table_name="market_memory_v2", timestamp_column="updated_at"),
    SourceRefreshRegistration("market_universe_memory", "MARKET_UNIVERSE", "SUPERVISOR_CYCLE", 86400, 3600, False, True, False, table_name="market_universe_memory", timestamp_column="updated_at"),
    SourceRefreshRegistration("source_event_memory", "SOURCE_EVENT_MEMORY", "SUPERVISOR_CYCLE", 3600, 900, False, True, True, table_name="source_event_memory", timestamp_column="updated_at"),
    SourceRefreshRegistration("targeted_market_revalidation", "TARGETED_REVALIDATION", "SUPERVISOR_CYCLE", 900, 900, False, True, True, table_name="targeted_market_revalidations", timestamp_column="updated_at"),
    SourceRefreshRegistration("proactive_candidate_generation", "PROACTIVE_CANDIDATE_GENERATION", "SUPERVISOR_CYCLE", 900, 900, True, True, True, table_name="proactive_candidate_seeds", timestamp_column="updated_at"),
    SourceRefreshRegistration("research_priority_watchlist", "RESEARCH_PRIORITY", "SUPERVISOR_CYCLE", 900, 900, False, True, False, table_name="research_priority_watchlist", timestamp_column="updated_at"),
    SourceRefreshRegistration("multi_trigger_candidate_generation", "MULTI_TRIGGER_CANDIDATE_GENERATION", "SUPERVISOR_CYCLE", 900, 900, True, True, True, table_name="multi_trigger_candidate_triggers", timestamp_column="updated_at"),
    SourceRefreshRegistration("proactive_seed_mesh_inquiry", "SEED_MESH_INQUIRY", "SUPERVISOR_CYCLE", 900, 900, True, True, True, table_name="proactive_seed_mesh_inquiries", timestamp_column="updated_at"),
    SourceRefreshRegistration("proactive_seed_mesh_adapter", "SEED_MESH_ADAPTER", "SUPERVISOR_CYCLE", 900, 900, True, True, True, table_name="proactive_seed_mesh_adapter_payloads", timestamp_column="updated_at"),
    SourceRefreshRegistration("ai_mesh_intelligence", "AI_MESH_INTELLIGENCE", "SUPERVISOR_CYCLE", 1800, 900, True, True, True, table_name="ai_mesh_insights", timestamp_column="updated_at"),
    SourceRefreshRegistration("neuron_signals", "SIGNAL", "PASSIVE", 900, 300, False, True, True, table_name="neuron_signals", timestamp_column="created_at"),
    SourceRefreshRegistration("signal_quality", "SIGNAL", "PASSIVE", 900, 300, False, True, True, table_name="signal_quality_evaluations", timestamp_column="evaluated_at"),
    SourceRefreshRegistration("payout", "PAYOUT", "SUPERVISOR_CYCLE", 900, 300, True, True, True, table_name="payout_odds_evaluations", timestamp_column="updated_at"),
    SourceRefreshRegistration("news", "NEWS", "SUPERVISOR_CYCLE", 5400, 900, False, True, True, required_config_keys=("NEWS_API_KEY", "NEWS_RSS_FEEDS", "CRYPTOPANIC_API_KEY"), table_name="news_impact_scores", timestamp_column="created_at"),
    SourceRefreshRegistration("whale", "WHALE", "SUPERVISOR_CYCLE", 5400, 900, False, True, True, required_config_keys=("POLYMARKET_CLOB_API_KEY", "POLYMARKET_CLOB_SECRET", "POLYMARKET_CLOB_PASSPHRASE"), table_name="whale_events", timestamp_column="event_time"),
    SourceRefreshRegistration("cross_market", "CROSS_MARKET", "UNAVAILABLE", 900, 900, False, True, True, table_name=None, timestamp_column=None),
    SourceRefreshRegistration("social", "SOCIAL", "UNAVAILABLE", 5400, 3600, False, True, True, required_config_keys=("X_BEARER_TOKEN", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"), table_name="social_market_links", timestamp_column="created_at"),
    SourceRefreshRegistration("ai_reasoner", "AI", "PASSIVE", 3600, 900, False, True, False, required_config_keys=("OLLAMA_BASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"), table_name=None, timestamp_column=None),
)


class SourceRefreshOrchestrator:
    """TTL-aware DATA_ONLY source refresh and derived signal producer.

    The orchestrator writes only source refresh truth rows and DATA_ONLY
    evidence rows. It never creates intents, orders, fills, positions, or
    capital ledger mutations.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        governor: StateGovernor | None = None,
        market_neuron: MarketNeuronService | None = None,
        payout_odds: PayoutOddsService | None = None,
        news: NewsNeuronService | None = None,
        whale: WhaleNeuronService | None = None,
        market_memory: MarketMemoryService | None = None,
        market_universe_memory: MarketUniverseMemoryService | None = None,
        source_event_memory: SourceEventMemoryService | None = None,
        targeted_revalidation: TargetedMarketRevalidationService | None = None,
        proactive_candidate_generation: ProactiveCandidateGenerationService | None = None,
        research_priority_watchlist: ResearchPriorityWatchlistService | None = None,
        multi_trigger_candidate_generation: MultiTriggerProactiveCandidateGeneratorService | None = None,
        proactive_seed_mesh_inquiry: ProactiveSeedMeshInquiryService | None = None,
        proactive_seed_mesh_adapter: ProactiveSeedDataOnlyMeshAdapter | None = None,
        ai_mesh_intelligence: AIMarketIntelligenceMeshOrgan | None = None,
        risk_evidence: RiskEvidenceMeshService | None = None,
        trade_thesis: TradeThesisEngine | None = None,
        capital_efficiency: CapitalEfficiencyService | None = None,
        trade_lifecycle: TradeLifecycleService | None = None,
        lifecycle_governance: LifecycleGovernanceGateService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._market_neuron = market_neuron or MarketNeuronService(connection_factory=self._factory, state_governor=self._governor)
        self._payout = payout_odds or PayoutOddsService(connection_factory=self._factory)
        self._news = news or NewsNeuronService(connection_factory=self._factory, state_governor=self._governor)
        self._whale = whale or WhaleNeuronService(connection_factory=self._factory, state_governor=self._governor)
        self._market_memory = market_memory or MarketMemoryService(connection_factory=self._factory, state_governor=self._governor)
        self._market_universe_memory = market_universe_memory or MarketUniverseMemoryService(connection_factory=self._factory)
        self._source_event_memory = source_event_memory or SourceEventMemoryService(connection_factory=self._factory)
        self._targeted_revalidation = targeted_revalidation or TargetedMarketRevalidationService(connection_factory=self._factory)
        self._proactive_candidate_generation = proactive_candidate_generation or ProactiveCandidateGenerationService(connection_factory=self._factory)
        self._research_priority_watchlist = research_priority_watchlist or ResearchPriorityWatchlistService(connection_factory=self._factory)
        self._multi_trigger_candidate_generation = multi_trigger_candidate_generation or MultiTriggerProactiveCandidateGeneratorService(connection_factory=self._factory)
        self._proactive_seed_mesh_inquiry = proactive_seed_mesh_inquiry or ProactiveSeedMeshInquiryService(connection_factory=self._factory)
        self._proactive_seed_mesh_adapter = proactive_seed_mesh_adapter or ProactiveSeedDataOnlyMeshAdapter(connection_factory=self._factory)
        self._ai_mesh_intelligence = ai_mesh_intelligence or AIMarketIntelligenceMeshOrgan(
            connection_factory=self._factory,
            config=AIMeshConfig(max_ai_calls=1, max_reasoning_calls=0, fast_timeout_seconds=18.0, reasoning_timeout_seconds=18.0, max_prompt_chars=700, fast_num_predict=220, reasoning_num_predict=140),
        )
        self._risk_evidence = risk_evidence or RiskEvidenceMeshService(connection_factory=self._factory)
        self._trade_thesis = trade_thesis or TradeThesisEngine(connection_factory=self._factory)
        self._capital_efficiency = capital_efficiency or CapitalEfficiencyService(connection_factory=self._factory)
        self._trade_lifecycle = trade_lifecycle or TradeLifecycleService(connection_factory=self._factory)
        self._lifecycle_governance = lifecycle_governance or LifecycleGovernanceGateService(connection_factory=self._factory)

    def run_cycle(self, *, candidate_limit: int = 20, news_limit: int = 5, whale_limit: int = 5) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        if not self._factory.enabled:
            return {
                "status": "DATABASE_UNAVAILABLE",
                "orchestrator_state": "BLOCKED",
                "sources_checked": len(SOURCE_REFRESH_REGISTRY),
                "sources_refreshed": 0,
                "sources_failed": 0,
                "sources_no_new_data": len(SOURCE_REFRESH_REGISTRY),
                "derived_signals_created": 0,
                "contracts": [self._contract_from_registration(reg, refresh_state="NO_CONNECTOR", attempt_at=started_at).to_api_dict() for reg in SOURCE_REFRESH_REGISTRY],
            }
        if not self._governor.can_execute(RuntimeAction.COLLECT_DATA):
            contracts = [self._contract_from_registration(reg, refresh_state="DISABLED", attempt_at=started_at, blocker="SOURCE_REFRESH_BLOCKED_BY_GOVERNOR") for reg in SOURCE_REFRESH_REGISTRY]
            self._persist_contracts(contracts, cycle_id=f"source_refresh_{uuid4().hex}", started_at=started_at, completed_at=datetime.now(UTC), metadata={"blocked": "State Governor denied COLLECT_DATA"})
            return _summary_payload("BLOCKED", started_at, contracts, derived_signals_created=0)

        cycle_id = f"source_refresh_{uuid4().hex}"
        contracts: list[SourceRefreshContract] = []
        derived_created = 0
        source_outcomes: dict[str, dict[str, Any]] = {}
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            safety_before = _safety_counts(conn)
            candidates = _candidate_orderbook_targets(conn, limit=candidate_limit)

        technical_result = self._produce_derived_signals(candidates)
        derived_created += _int(technical_result.get("derived_signals_created"))
        source_outcomes["orderbook_signals"] = technical_result
        source_outcomes["market_movement"] = technical_result
        source_outcomes["market_technical_signals"] = technical_result
        source_outcomes["liquidity"] = technical_result

        payout_result = self._refresh_payout(limit=max(candidate_limit, 20))
        source_outcomes["payout"] = payout_result
        news_result = self._refresh_news(limit_per_source=news_limit)
        source_outcomes["news"] = news_result
        whale_result = self._refresh_whale(limit_per_source=whale_limit)
        source_outcomes["whale"] = whale_result
        memory_result = self._refresh_memory(candidates)
        source_outcomes["market_memory_v2"] = memory_result
        universe_result = self._refresh_market_universe_memory()
        source_outcomes["market_universe_memory"] = universe_result
        source_event_result = self._refresh_source_event_memory()
        source_outcomes["source_event_memory"] = source_event_result
        targeted_revalidation_result = self._refresh_targeted_market_revalidation()
        source_outcomes["targeted_market_revalidation"] = targeted_revalidation_result
        proactive_candidate_generation_result = self._refresh_proactive_candidate_generation()
        source_outcomes["proactive_candidate_generation"] = proactive_candidate_generation_result
        research_priority_watchlist_result = self._refresh_research_priority_watchlist()
        source_outcomes["research_priority_watchlist"] = research_priority_watchlist_result
        multi_trigger_candidate_generation_result = self._refresh_multi_trigger_candidate_generation()
        source_outcomes["multi_trigger_candidate_generation"] = multi_trigger_candidate_generation_result
        proactive_seed_mesh_inquiry_result = self._refresh_proactive_seed_mesh_inquiry()
        source_outcomes["proactive_seed_mesh_inquiry"] = proactive_seed_mesh_inquiry_result
        proactive_seed_mesh_adapter_result = self._refresh_proactive_seed_mesh_adapter()
        source_outcomes["proactive_seed_mesh_adapter"] = proactive_seed_mesh_adapter_result
        ai_mesh_intelligence_result = self._refresh_ai_mesh_intelligence()
        source_outcomes["ai_mesh_intelligence"] = ai_mesh_intelligence_result

        with self._factory.connect() as conn:
            safety_after = _safety_counts(conn)
            for reg in SOURCE_REFRESH_REGISTRY:
                contracts.append(self._contract_for_source(conn, reg, source_outcomes.get(reg.source_name), attempt_at=started_at))
            completed_at = datetime.now(UTC)
            metadata = {
                "candidate_targets": len(candidates),
                "source_outcomes": source_outcomes,
                "safety_before": safety_before,
                "safety_after": safety_after,
                "trading_mutation": _trading_mutation(safety_before, safety_after),
            }
            self._persist_contracts(contracts, cycle_id=cycle_id, started_at=started_at, completed_at=completed_at, metadata=metadata)

        downstream_result = self._refresh_downstream_decision_truth(limit=max(candidate_limit, 20))
        source_outcomes["risk_lifecycle_recompute"] = downstream_result
        self._persist_downstream_outcome(cycle_id, downstream_result)

        payload = _summary_payload("ACTIVE", started_at, contracts, derived_signals_created=derived_created)
        payload["cycle_id"] = cycle_id
        payload["source_outcomes"] = source_outcomes
        payload["safety_before"] = safety_before
        payload["safety_after"] = safety_after
        payload["trading_mutation"] = _trading_mutation(safety_before, safety_after)
        return payload

    def status(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        if not self._factory.enabled:
            contracts = [self._contract_from_registration(reg, refresh_state="NO_CONNECTOR").to_api_dict() for reg in SOURCE_REFRESH_REGISTRY]
            return _status_payload("MISSING", now, contracts, cycles_completed=0, latest_cycle=None)
        with self._factory.connect() as conn:
            self._ensure_tables(conn)
            rows = conn.execute(
                """
                SELECT *
                FROM source_refresh_status
                ORDER BY source_name
                """
            ).fetchall()
            latest_cycle = conn.execute(
                """
                SELECT *
                FROM source_refresh_cycles
                ORDER BY completed_at DESC NULLS LAST, id DESC
                LIMIT 1
                """
            ).fetchone()
            cycles = conn.execute("SELECT COUNT(*) AS count FROM source_refresh_cycles").fetchone()["count"]
            downstream = _latest_downstream_context(conn)
            if not rows:
                contracts = [self._contract_for_source(conn, reg, None).to_api_dict() for reg in SOURCE_REFRESH_REGISTRY]
            else:
                contracts = [_row_to_api(dict(row)) for row in rows]
        payload = _status_payload("REAL" if contracts else "MISSING", now, contracts, cycles_completed=int(cycles or 0), latest_cycle=_row_to_api(dict(latest_cycle)) if latest_cycle else None)
        payload.update(downstream)
        return payload

    def _produce_derived_signals(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        if not candidates:
            return {"status": "NO_TARGETS", "derived_signals_created": 0, "targets_checked": 0}
        before = self._count_table("market_technical_signals") + self._count_table("orderbook_signals")
        outcomes: list[dict[str, Any]] = []
        for candidate in candidates:
            try:
                outcomes.append(
                    self._market_neuron.analyze_market(
                        str(candidate["market_id"]),
                        token_id=str(candidate.get("token_id") or "") or None,
                        side=str(candidate.get("side") or "UNKNOWN"),
                    )
                )
            except Exception as exc:
                outcomes.append({"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "market_id": candidate.get("market_id")})
        after = self._count_table("market_technical_signals") + self._count_table("orderbook_signals")
        errors = [item for item in outcomes if item.get("status") == "FAILED_WITH_ERROR" or item.get("error")]
        return {
            "status": "FAILED_WITH_ERROR" if errors and len(errors) == len(outcomes) else "OK",
            "targets_checked": len(candidates),
            "derived_signals_created": max(0, after - before),
            "errors": errors[:5],
        }

    def _refresh_payout(self, *, limit: int) -> dict[str, Any]:
        try:
            return self._payout.evaluate_recent(limit=limit, subject_type="PAPER_CANDIDATE", dry_run=False)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "evaluations_created": 0}

    def _refresh_news(self, *, limit_per_source: int) -> dict[str, Any]:
        try:
            result = self._news.collect_and_process_sources(limit_per_source=limit_per_source, analyze_with_ai=False)
            if int(result.get("raw_events") or 0) == 0:
                result["status"] = "REFRESHING_NO_NEW_DATA"
            else:
                result["status"] = "OK"
            return result
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "raw_events": 0}

    def _refresh_whale(self, *, limit_per_source: int) -> dict[str, Any]:
        try:
            result = self._whale.scan_and_process_sources(limit_per_source=limit_per_source, analyze_with_ai=False)
            if int(result.get("raw_events") or 0) == 0:
                result["status"] = "REFRESHING_NO_NEW_DATA"
            else:
                result["status"] = "OK"
            return result
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "raw_events": 0}

    def _refresh_memory(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        if not candidates:
            return {"status": "NO_TARGETS", "written": False, "reason": "MARKET_MEMORY_NO_HISTORICAL_OUTCOME_SOURCE"}
        # Market memory is safe only after technical rows exist. It may still
        # record insufficient-data memory, but never invents hit rates.
        try:
            market_id = str(candidates[0]["market_id"])
            return self._market_memory.rebuild(market_id=market_id, dry_run=False)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "written": False}

    def _refresh_market_universe_memory(self) -> dict[str, Any]:
        try:
            return self._market_universe_memory.refresh_universe(force=False, min_interval_seconds=3600)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "markets_seen": 0}

    def _refresh_source_event_memory(self) -> dict[str, Any]:
        try:
            return self._source_event_memory.refresh_events(force=False, window_hours=72, max_events=500)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "events_seen": 0}

    def _refresh_targeted_market_revalidation(self) -> dict[str, Any]:
        try:
            return self._targeted_revalidation.refresh(limit=20, force=False, skipped_sample_limit=5)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "eligible_links_seen": 0}

    def _refresh_proactive_candidate_generation(self) -> dict[str, Any]:
        try:
            return self._proactive_candidate_generation.refresh(limit=20, force=False, blocked_sample_limit=5)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "revalidation_rows_seen": 0}

    def _refresh_research_priority_watchlist(self) -> dict[str, Any]:
        try:
            return self._research_priority_watchlist.refresh(limit=200, force=False)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "markets_seen": 0}

    def _refresh_multi_trigger_candidate_generation(self) -> dict[str, Any]:
        try:
            return self._multi_trigger_candidate_generation.refresh(limit=20, force=False)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "triggers_detected": 0}

    def _refresh_proactive_seed_mesh_inquiry(self) -> dict[str, Any]:
        try:
            return self._proactive_seed_mesh_inquiry.refresh(limit=20, force=False)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "seeds_available": 0}

    def _refresh_proactive_seed_mesh_adapter(self) -> dict[str, Any]:
        try:
            return self._proactive_seed_mesh_adapter.run(limit=10, force=False)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "eligible_requests": 0}

    def _refresh_ai_mesh_intelligence(self) -> dict[str, Any]:
        try:
            return self._ai_mesh_intelligence.refresh(limit=2, force=False)
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "insights_created": 0}

    def _refresh_downstream_decision_truth(self, *, limit: int) -> dict[str, Any]:
        """Recompute DATA_ONLY Risk/Lifecycle rows after source freshness changes."""
        try:
            initial_risk = self._risk_evidence.evaluate_recent(limit=limit, subject_type="PAPER_CANDIDATE", dry_run=False)
            thesis = self._trade_thesis.evaluate_recent(limit=limit, subject_type="PAPER_CANDIDATE", dry_run=False)
            capital = self._capital_efficiency.evaluate_recent(limit=limit, subject_type="PAPER_CANDIDATE", dry_run=False)
            risk = self._risk_evidence.evaluate_recent(limit=limit, subject_type="PAPER_CANDIDATE", dry_run=False)
            lifecycle = self._trade_lifecycle.build_recent(limit=limit, subject_type="PAPER_CANDIDATE", dry_run=False)
            governance = self._lifecycle_governance.evaluate_recent(limit=limit, subject_type="PAPER_CANDIDATE", dry_run=False)
            return {
                "status": "OK",
                "initial_risk_evidence": initial_risk,
                "trade_thesis": thesis,
                "capital_efficiency": capital,
                "risk_evidence": risk,
                "trade_lifecycle": lifecycle,
                "lifecycle_governance": governance,
                "trading_mutation": bool(initial_risk.get("trading_mutation") or thesis.get("trading_mutation") or capital.get("trading_mutation") or risk.get("trading_mutation") or lifecycle.get("trading_mutation") or governance.get("trading_mutation")),
            }
        except Exception as exc:
            return {"status": "FAILED_WITH_ERROR", "error": f"{type(exc).__name__}: {exc}", "trading_mutation": False}

    def _persist_downstream_outcome(self, cycle_id: str, outcome: dict[str, Any]) -> None:
        try:
            with self._factory.connect() as conn:
                self._ensure_tables(conn)
                conn.execute(
                    """
                    UPDATE source_refresh_cycles
                    SET metadata_json = metadata_json || jsonb_build_object(
                        'downstream_decision_truth', %s::jsonb,
                        'source_outcomes', COALESCE(metadata_json->'source_outcomes', '{}'::jsonb) || jsonb_build_object('risk_lifecycle_recompute', %s::jsonb)
                    )
                    WHERE cycle_id=%s
                    """,
                    (_json_dumps(outcome), _json_dumps(outcome), cycle_id),
                )
        except Exception:
            return None

    def _contract_for_source(self, conn: Any, reg: SourceRefreshRegistration, outcome: dict[str, Any] | None, *, attempt_at: datetime | None = None) -> SourceRefreshContract:
        stats = _table_stats(conn, reg.table_name, reg.timestamp_column)
        outcome_status = str((outcome or {}).get("status") or "")
        latest_data_at = stats["latest_data_at"]
        freshness = _age_seconds(latest_data_at)
        missing_config = _missing_config_keys(conn, reg)
        error = _error_code(outcome)
        state = _classify_state(reg, outcome_status, stats, freshness, missing_config, error)
        success_at = attempt_at if state in {"FRESH", "REFRESHING_NO_NEW_DATA", "REFRESHING_BUT_NOT_CANDIDATE_LINKED", "REFRESHING_BUT_NOT_DIRECTIONAL"} else None
        return SourceRefreshContract(
            source_name=reg.source_name,
            source_type=reg.source_type,
            enabled=state not in {"DISABLED", "KNOWN_NOT_IMPLEMENTED"},
            refresh_mode=reg.refresh_mode,
            candidate_scoped_supported=reg.candidate_scoped_supported,
            market_level_supported=reg.market_level_supported,
            directional_supported=reg.directional_supported,
            last_refresh_attempt_at=attempt_at,
            last_successful_refresh_at=success_at,
            latest_data_at=latest_data_at,
            latest_error_at=attempt_at if error else None,
            latest_error_code=error,
            refresh_interval_seconds=reg.refresh_interval_seconds,
            ttl_seconds=reg.ttl_seconds,
            freshness_seconds=freshness,
            refresh_state=state,
            rows_total=stats["rows_total"],
            rows_last_24h=stats["rows_last_24h"],
            rows_last_1h=stats["rows_last_1h"],
            rows_last_15m=stats["rows_last_15m"],
            candidate_linked_rows=stats["candidate_linked_rows"],
            directional_rows=stats["directional_rows"],
            safe_to_refresh_data_only=reg.safe_to_refresh_data_only,
            required_config_keys=list(reg.required_config_keys),
            missing_config_keys=missing_config,
            blocker_code=_blocker_for_state(state, reg),
            required_to_pass=_required_for_state(state, reg, missing_config),
            metadata={"outcome": outcome or {}, "table_name": reg.table_name, "timestamp_column": reg.timestamp_column},
        )

    def _contract_from_registration(
        self,
        reg: SourceRefreshRegistration,
        *,
        refresh_state: str,
        attempt_at: datetime | None = None,
        blocker: str | None = None,
    ) -> SourceRefreshContract:
        return SourceRefreshContract(
            source_name=reg.source_name,
            source_type=reg.source_type,
            enabled=refresh_state not in {"DISABLED", "KNOWN_NOT_IMPLEMENTED"},
            refresh_mode=reg.refresh_mode,
            candidate_scoped_supported=reg.candidate_scoped_supported,
            market_level_supported=reg.market_level_supported,
            directional_supported=reg.directional_supported,
            last_refresh_attempt_at=attempt_at,
            refresh_interval_seconds=reg.refresh_interval_seconds,
            ttl_seconds=reg.ttl_seconds,
            refresh_state=refresh_state,
            safe_to_refresh_data_only=reg.safe_to_refresh_data_only,
            required_config_keys=list(reg.required_config_keys),
            blocker_code=blocker or _blocker_for_state(refresh_state, reg),
            required_to_pass=_required_for_state(refresh_state, reg, []),
        )

    def _persist_contracts(self, contracts: list[SourceRefreshContract], *, cycle_id: str, started_at: datetime, completed_at: datetime, metadata: dict[str, Any]) -> None:
        with self._factory.connect() as conn, conn.transaction():
            self._ensure_tables(conn)
            sources_failed = sum(1 for item in contracts if item.refresh_state == "FAILED_WITH_ERROR")
            no_new = sum(1 for item in contracts if item.refresh_state in {"REFRESHING_NO_NEW_DATA", "NO_REFRESH_PRODUCER", "NO_CONNECTOR", "MISSING_CONFIG", "KNOWN_NOT_IMPLEMENTED"})
            refreshed = sum(1 for item in contracts if item.refresh_state in {"FRESH", "REFRESHING_NO_NEW_DATA", "REFRESHING_BUT_NOT_CANDIDATE_LINKED", "REFRESHING_BUT_NOT_DIRECTIONAL"})
            conn.execute(
                """
                INSERT INTO source_refresh_cycles (
                    cycle_id, orchestrator_state, sources_checked, sources_refreshed, sources_failed,
                    sources_no_new_data, derived_signals_created, started_at, completed_at, metadata_json
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (cycle_id) DO NOTHING
                """,
                (
                    cycle_id,
                    "ACTIVE" if sources_failed == 0 else "PARTIAL",
                    len(contracts),
                    refreshed,
                    sources_failed,
                    no_new,
                    int((metadata.get("source_outcomes") or {}).get("market_technical_signals", {}).get("derived_signals_created") or 0),
                    started_at,
                    completed_at,
                    Jsonb(_jsonable(metadata)),
                ),
            )
            for contract in contracts:
                row = contract.to_row()
                conn.execute(
                    """
                    INSERT INTO source_refresh_status (
                        source_name, source_type, enabled, refresh_mode, candidate_scoped_supported,
                        market_level_supported, directional_supported, last_refresh_attempt_at,
                        last_successful_refresh_at, latest_data_at, latest_error_at, latest_error_code,
                        refresh_interval_seconds, ttl_seconds, freshness_seconds, refresh_state,
                        rows_total, rows_last_24h, rows_last_1h, rows_last_15m, candidate_linked_rows,
                        directional_rows, safe_to_refresh_data_only, required_config_keys,
                        missing_config_keys, blocker_code, required_to_pass, metadata_json
                    )
                    VALUES (
                        %(source_name)s, %(source_type)s, %(enabled)s, %(refresh_mode)s, %(candidate_scoped_supported)s,
                        %(market_level_supported)s, %(directional_supported)s, %(last_refresh_attempt_at)s,
                        %(last_successful_refresh_at)s, %(latest_data_at)s, %(latest_error_at)s, %(latest_error_code)s,
                        %(refresh_interval_seconds)s, %(ttl_seconds)s, %(freshness_seconds)s, %(refresh_state)s,
                        %(rows_total)s, %(rows_last_24h)s, %(rows_last_1h)s, %(rows_last_15m)s, %(candidate_linked_rows)s,
                        %(directional_rows)s, %(safe_to_refresh_data_only)s, %(required_config_keys)s,
                        %(missing_config_keys)s, %(blocker_code)s, %(required_to_pass)s, %(metadata_json)s
                    )
                    ON CONFLICT (source_name) DO UPDATE SET
                        source_type=EXCLUDED.source_type,
                        enabled=EXCLUDED.enabled,
                        refresh_mode=EXCLUDED.refresh_mode,
                        candidate_scoped_supported=EXCLUDED.candidate_scoped_supported,
                        market_level_supported=EXCLUDED.market_level_supported,
                        directional_supported=EXCLUDED.directional_supported,
                        last_refresh_attempt_at=EXCLUDED.last_refresh_attempt_at,
                        last_successful_refresh_at=COALESCE(EXCLUDED.last_successful_refresh_at, source_refresh_status.last_successful_refresh_at),
                        latest_data_at=EXCLUDED.latest_data_at,
                        latest_error_at=EXCLUDED.latest_error_at,
                        latest_error_code=EXCLUDED.latest_error_code,
                        refresh_interval_seconds=EXCLUDED.refresh_interval_seconds,
                        ttl_seconds=EXCLUDED.ttl_seconds,
                        freshness_seconds=EXCLUDED.freshness_seconds,
                        refresh_state=EXCLUDED.refresh_state,
                        rows_total=EXCLUDED.rows_total,
                        rows_last_24h=EXCLUDED.rows_last_24h,
                        rows_last_1h=EXCLUDED.rows_last_1h,
                        rows_last_15m=EXCLUDED.rows_last_15m,
                        candidate_linked_rows=EXCLUDED.candidate_linked_rows,
                        directional_rows=EXCLUDED.directional_rows,
                        safe_to_refresh_data_only=TRUE,
                        required_config_keys=EXCLUDED.required_config_keys,
                        missing_config_keys=EXCLUDED.missing_config_keys,
                        blocker_code=EXCLUDED.blocker_code,
                        required_to_pass=EXCLUDED.required_to_pass,
                        metadata_json=EXCLUDED.metadata_json,
                        updated_at=now()
                    """,
                    {
                        **row,
                        "required_config_keys": Jsonb(row["required_config_keys"]),
                        "missing_config_keys": Jsonb(row["missing_config_keys"]),
                        "required_to_pass": Jsonb(row["required_to_pass"]),
                        "metadata_json": Jsonb(_jsonable(row["metadata_json"])),
                    },
                )

    def _count_table(self, table: str) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            if not _table_exists(conn, table):
                return 0
            return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)

    def _ensure_tables(self, conn: Any) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_refresh_cycles (
                id bigserial PRIMARY KEY,
                cycle_id text NOT NULL UNIQUE,
                orchestrator_state text NOT NULL,
                sources_checked integer NOT NULL DEFAULT 0,
                sources_refreshed integer NOT NULL DEFAULT 0,
                sources_failed integer NOT NULL DEFAULT 0,
                sources_no_new_data integer NOT NULL DEFAULT 0,
                derived_signals_created integer NOT NULL DEFAULT 0,
                started_at timestamptz NOT NULL DEFAULT now(),
                completed_at timestamptz NULL,
                metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS source_refresh_status (
                id bigserial PRIMARY KEY,
                source_name text NOT NULL UNIQUE,
                source_type text NOT NULL,
                enabled boolean NOT NULL DEFAULT true,
                refresh_mode text NOT NULL,
                candidate_scoped_supported boolean NOT NULL DEFAULT false,
                market_level_supported boolean NOT NULL DEFAULT true,
                directional_supported boolean NOT NULL DEFAULT false,
                last_refresh_attempt_at timestamptz NULL,
                last_successful_refresh_at timestamptz NULL,
                latest_data_at timestamptz NULL,
                latest_error_at timestamptz NULL,
                latest_error_code text NULL,
                refresh_interval_seconds integer NOT NULL DEFAULT 0,
                ttl_seconds integer NOT NULL DEFAULT 0,
                freshness_seconds integer NULL,
                refresh_state text NOT NULL DEFAULT 'UNKNOWN',
                rows_total integer NOT NULL DEFAULT 0,
                rows_last_24h integer NOT NULL DEFAULT 0,
                rows_last_1h integer NOT NULL DEFAULT 0,
                rows_last_15m integer NOT NULL DEFAULT 0,
                candidate_linked_rows integer NOT NULL DEFAULT 0,
                directional_rows integer NOT NULL DEFAULT 0,
                safe_to_refresh_data_only boolean NOT NULL DEFAULT true,
                required_config_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
                missing_config_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
                blocker_code text NULL,
                required_to_pass jsonb NOT NULL DEFAULT '[]'::jsonb,
                metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamptz NOT NULL DEFAULT now(),
                updated_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )


def registry() -> list[SourceRefreshRegistration]:
    return list(SOURCE_REFRESH_REGISTRY)


def _candidate_orderbook_targets(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    if not _table_exists(conn, "orderbook_snapshots"):
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT ON (market_id, token_id, side)
               market_id, token_id, side, id AS orderbook_snapshot_id, snapshot_at, collected_at
        FROM orderbook_snapshots
        WHERE market_id IS NOT NULL
          AND token_id IS NOT NULL
          AND COALESCE(is_stale, false) = false
          AND best_ask IS NOT NULL
          AND best_bid IS NOT NULL
        ORDER BY market_id, token_id, side, snapshot_at DESC NULLS LAST, collected_at DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _table_stats(conn: Any, table: str | None, ts_col: str | None) -> dict[str, Any]:
    if not table or not _table_exists(conn, table):
        return {"rows_total": 0, "rows_last_24h": 0, "rows_last_1h": 0, "rows_last_15m": 0, "candidate_linked_rows": 0, "directional_rows": 0, "latest_data_at": None}
    cols = _columns(conn, table)
    rows_total = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
    latest = None
    rows_24 = rows_1 = rows_15 = 0
    if ts_col and ts_col in cols:
        latest = conn.execute(f"SELECT MAX({ts_col}) AS latest FROM {table}").fetchone()["latest"]
        rows_24 = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {ts_col} >= now() - interval '24 hours'").fetchone()["count"] or 0)
        rows_1 = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {ts_col} >= now() - interval '1 hour'").fetchone()["count"] or 0)
        rows_15 = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {ts_col} >= now() - interval '15 minutes'").fetchone()["count"] or 0)
    candidate_cols = [col for col in ("candidate_id", "subject_id", "token_id", "correlation_id") if col in cols]
    candidate_linked = 0
    if candidate_cols:
        predicate = " OR ".join(f"{col} IS NOT NULL" for col in candidate_cols)
        candidate_linked = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}").fetchone()["count"] or 0)
    direction_cols = [col for col in ("direction", "side", "matched_side", "raw_direction", "trend_direction") if col in cols]
    directional = 0
    if direction_cols:
        predicate = " OR ".join(f"UPPER(COALESCE({col}::text,'')) IN ('YES','NO','UP','DOWN','BULLISH','BEARISH','POSITIVE','NEGATIVE')" for col in direction_cols)
        directional = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}").fetchone()["count"] or 0)
    return {
        "rows_total": rows_total,
        "rows_last_24h": rows_24,
        "rows_last_1h": rows_1,
        "rows_last_15m": rows_15,
        "candidate_linked_rows": candidate_linked,
        "directional_rows": directional,
        "latest_data_at": latest,
    }


def _missing_config_keys(conn: Any, reg: SourceRefreshRegistration) -> list[str]:
    if not reg.required_config_keys:
        return []
    if reg.source_name == "ai_reasoner":
        return list(reg.required_config_keys)
    if _table_exists(conn, "intelligence_source_credentials_status"):
        rows = conn.execute(
            """
            SELECT env_var
            FROM intelligence_source_credentials_status
            WHERE env_var = ANY(%s)
              AND required IS TRUE
              AND present IS FALSE
            """,
            (list(reg.required_config_keys),),
        ).fetchall()
        if rows:
            return sorted({str(row["env_var"]) for row in rows})
    return []


def _classify_state(reg: SourceRefreshRegistration, outcome_status: str, stats: dict[str, Any], freshness: int | None, missing_config: list[str], error: str | None) -> str:
    if reg.refresh_mode == "UNAVAILABLE":
        return "NO_CONNECTOR" if reg.source_name == "cross_market" else "KNOWN_NOT_IMPLEMENTED"
    if missing_config and stats["rows_total"] == 0:
        return "MISSING_CONFIG"
    if error:
        return "FAILED_WITH_ERROR"
    if outcome_status in {"REFRESHING_NO_NEW_DATA", "NO_TARGETS"}:
        return "REFRESHING_NO_NEW_DATA"
    if reg.table_name and stats["rows_total"] == 0:
        return "NO_REFRESH_PRODUCER" if reg.refresh_mode == "PASSIVE" else "REFRESHING_NO_NEW_DATA"
    if freshness is not None and reg.ttl_seconds and freshness > reg.ttl_seconds:
        return "STALE_BY_TTL"
    if reg.directional_supported and stats["directional_rows"] == 0:
        return "REFRESHING_BUT_NOT_DIRECTIONAL"
    if reg.candidate_scoped_supported and stats["candidate_linked_rows"] == 0:
        return "REFRESHING_BUT_NOT_CANDIDATE_LINKED"
    return "FRESH"


def _blocker_for_state(state: str, reg: SourceRefreshRegistration) -> str | None:
    if state in {"FRESH", "REFRESHING_NO_NEW_DATA"}:
        return None
    return f"{reg.source_name.upper()}_{state}"


def _required_for_state(state: str, reg: SourceRefreshRegistration, missing_config: list[str]) -> list[str]:
    if state in {"FRESH", "REFRESHING_NO_NEW_DATA"}:
        return []
    if state == "MISSING_CONFIG":
        return [f"Configure {key} or keep {reg.source_name} unavailable." for key in missing_config]
    if state == "NO_CONNECTOR":
        return [f"Add a real {reg.source_name} connector before using it for source-backed edge."]
    if state == "STALE_BY_TTL":
        return [f"Refresh {reg.source_name} within TTL {reg.ttl_seconds}s."]
    if state == "REFRESHING_BUT_NOT_DIRECTIONAL":
        return [f"{reg.source_name} must produce directional YES/NO/CONFLICT evidence to affect Edge."]
    if state == "REFRESHING_BUT_NOT_CANDIDATE_LINKED":
        return [f"{reg.source_name} must link to candidate market/side/token."]
    return [f"Resolve {reg.source_name} refresh state {state}."]


def _error_code(outcome: dict[str, Any] | None) -> str | None:
    if not outcome:
        return None
    if outcome.get("error"):
        return str(outcome.get("error"))[:240]
    if str(outcome.get("status") or "") == "FAILED_WITH_ERROR":
        return "FAILED_WITH_ERROR"
    return None


def _summary_payload(state: str, started_at: datetime, contracts: list[SourceRefreshContract], *, derived_signals_created: int) -> dict[str, Any]:
    failed = [item for item in contracts if item.refresh_state == "FAILED_WITH_ERROR"]
    no_new = [item for item in contracts if item.refresh_state in {"REFRESHING_NO_NEW_DATA", "NO_CONNECTOR", "NO_REFRESH_PRODUCER", "MISSING_CONFIG", "KNOWN_NOT_IMPLEMENTED"}]
    refreshed = [item for item in contracts if item.refresh_state in {"FRESH", "REFRESHING_NO_NEW_DATA", "REFRESHING_BUT_NOT_CANDIDATE_LINKED", "REFRESHING_BUT_NOT_DIRECTIONAL"}]
    return {
        "status": "OK" if not failed else "PARTIAL",
        "orchestrator_state": state,
        "generated_at": datetime.now(UTC).isoformat(),
        "latest_source_refresh_at": started_at.isoformat(),
        "sources_checked": len(contracts),
        "sources_refreshed": len(refreshed),
        "sources_failed": len(failed),
        "sources_no_new_data": len(no_new),
        "derived_signals_created": derived_signals_created,
        "contracts": [item.to_api_dict() for item in contracts],
    }


def _status_payload(status: str, now: datetime, contracts: list[dict[str, Any]], *, cycles_completed: int, latest_cycle: dict[str, Any] | None) -> dict[str, Any]:
    stale = [item for item in contracts if item.get("refresh_state") == "STALE_BY_TTL"]
    failed = [item for item in contracts if item.get("refresh_state") == "FAILED_WITH_ERROR"]
    missing = [item for item in contracts if item.get("refresh_state") in {"MISSING_CONFIG", "NO_CONNECTOR", "NO_REFRESH_PRODUCER", "KNOWN_NOT_IMPLEMENTED"}]
    no_new = [item for item in contracts if item.get("refresh_state") == "REFRESHING_NO_NEW_DATA"]
    return {
        "status": status,
        "source": "source_refresh_status + source_refresh_cycles",
        "last_updated": (latest_cycle or {}).get("completed_at") or now.isoformat(),
        "freshness_state": "FRESH" if contracts and not stale and not failed else "PARTIAL" if contracts else "MISSING",
        "readiness_state": "READY" if contracts and not failed else "PARTIAL" if contracts else "UNKNOWN",
        "truth_state": "ACTIVE_FRESH" if contracts else "UNKNOWN",
        "source_refresh_orchestrator_state": "ACTIVE" if cycles_completed else "NOT_STARTED",
        "cycles_completed": cycles_completed,
        "latest_cycle": latest_cycle,
        "counts": {
            "sources": len(contracts),
            "fresh": sum(1 for item in contracts if item.get("refresh_state") == "FRESH"),
            "stale": len(stale),
            "failed": len(failed),
            "missing_or_no_connector": len(missing),
            "no_new_data": len(no_new),
            "derived_sources": sum(1 for item in contracts if item.get("refresh_mode") == "DERIVED"),
            "candidate_linked_rows": sum(int(item.get("candidate_linked_rows") or 0) for item in contracts),
            "directional_rows": sum(int(item.get("directional_rows") or 0) for item in contracts),
        },
        "stale_sources": [item.get("source_name") for item in stale],
        "failed_sources": [item.get("source_name") for item in failed],
        "missing_config_sources": [item.get("source_name") for item in contracts if item.get("refresh_state") == "MISSING_CONFIG"],
        "no_connector_sources": [item.get("source_name") for item in contracts if item.get("refresh_state") == "NO_CONNECTOR"],
        "no_new_data_sources": [item.get("source_name") for item in no_new],
        "per_source": contracts,
        "errors": [],
        "warnings": [] if contracts else ["Source refresh orchestrator has not produced status rows yet."],
    }


def _latest_downstream_context(conn: Any) -> dict[str, Any]:
    if not _table_exists(conn, "risk_evidence_mesh_evaluations"):
        return {
            "latest_source_refresh_cycle_id": None,
            "latest_downstream_edge_thesis_id": None,
            "latest_downstream_risk_evidence_id": None,
            "propagation_state": "BLOCKED",
            "propagation_breakpoint": "RISK_EVIDENCE_TABLE_MISSING",
        }
    row = conn.execute(
        """
        SELECT evaluation_id, metadata_json, updated_at, created_at
        FROM risk_evidence_mesh_evaluations
        WHERE metadata_json ? 'edge_thesis'
        ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return {
            "latest_source_refresh_cycle_id": None,
            "latest_downstream_edge_thesis_id": None,
            "latest_downstream_risk_evidence_id": None,
            "propagation_state": "BLOCKED",
            "propagation_breakpoint": "EDGE_THESIS_MISSING",
        }
    metadata = dict(row["metadata_json"] or {})
    thesis = metadata.get("edge_thesis") if isinstance(metadata.get("edge_thesis"), dict) else {}
    cycle_id = metadata.get("source_refresh_cycle_id") or thesis.get("source_refresh_cycle_id")
    return {
        "latest_source_refresh_cycle_id": cycle_id,
        "latest_downstream_edge_thesis_id": thesis.get("edge_thesis_id"),
        "latest_downstream_risk_evidence_id": row["evaluation_id"],
        "propagation_state": "ACTIVE" if cycle_id else "PARTIAL",
        "propagation_breakpoint": None if cycle_id else "SOURCE_REFRESH_CONTEXT_MISSING",
    }


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS reg", (table,)).fetchone()
    return bool(row and row["reg"])


def _columns(conn: Any, table: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


def _age_seconds(value: Any) -> int | None:
    if value is None:
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


def _row_to_api(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key, value in list(out.items()):
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    return value


def _json_dumps(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safety_counts(conn: Any) -> dict[str, int]:
    tables = ["paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "live_orders", "positions"]
    counts: dict[str, int] = {}
    for table in tables:
        if _table_exists(conn, table):
            counts[table] = int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
        else:
            counts[table] = 0
    return counts


def _trading_mutation(before: dict[str, int], after: dict[str, int]) -> bool:
    return any(int(after.get(key, 0)) > int(before.get(key, 0)) for key in before)
