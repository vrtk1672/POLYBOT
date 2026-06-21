from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.runtime.health_truth import HealthTruthService
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService
from app.services.impact_graph import ImpactGraphService
from app.services.position_thesis import PositionThesisService
from app.services.query.operator_dashboard_query_service import OperatorDashboardQueryService
from app.services.neuron_registry import NeuronRegistryService
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_lineage import SignalLineageService


_STALE_AFTER = timedelta(minutes=20)
_NO_DATA_STATUSES = {"EMPTY", "DISABLED", "ABSENT", "INSUFFICIENT_DATA", "NO_DATA"}


class DashboardV2QueryService:
    """DB/runtime truth adapter for the V2 operator cockpit.

    This class intentionally wraps existing dashboard/query surfaces instead of
    inventing a second truth path. Every page payload is read-only.
    """

    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._operator = OperatorDashboardQueryService(connection_factory=self._factory)

    def get_page(self, page: str, *, limit: int = 8) -> dict[str, object]:
        generated_at = datetime.now(UTC)
        page = page.replace("_", "-")
        loader = self._page_loaders(limit).get(page)
        if loader is None:
            return self._envelope(
                page=page,
                data={},
                generated_at=generated_at,
                errors=[f"unknown_dashboard_v2_page:{page}"],
                source_tables=[],
            )
        try:
            data, source_tables = loader()
            return self._envelope(
                page=page,
                data=data,
                generated_at=generated_at,
                errors=self._collect_errors(data),
                source_tables=source_tables,
            )
        except Exception as exc:
            return self._envelope(
                page=page,
                data={},
                generated_at=generated_at,
                errors=[str(exc)],
                source_tables=[],
            )

    def _page_loaders(self, limit: int) -> dict[str, Callable[[], tuple[dict[str, object], list[str]]]]:
        return {
            "overview": lambda: self._overview(limit),
            "events": lambda: self._events(limit),
            "signals": lambda: self._signals(limit),
            "signal-lineage": lambda: self._signal_lineage(limit),
            "brain-outputs": lambda: self._brain_outputs(limit),
            "coordinator": lambda: self._coordinator(limit),
            "impact-graph": lambda: self._impact_graph(limit),
            "thesis": lambda: self._thesis(limit),
            "neurons": lambda: self._neurons(),
            "risk": lambda: self._module("risk", self._operator._risk_overview(), ["risk_governor_state", "risk_gate_decisions", "risk_breaches", "cooldown_events"]),
            "engines": lambda: self._module("engines", self._operator._strategy_overview(), ["strategy_routes_v2", "engine_decisions", "engine_rejections", "engine_cooldowns"]),
            "ai": lambda: self._module("ai", self._operator._ai_brain_overview(), ["ai_requests", "ai_cost_ledger", "ai_cache", "ai_model_performance"]),
            "no-trade": lambda: self._module("no_trade", self._operator._no_trade_overview(), ["no_trade_log", "no_trade_reasons", "no_trade_post_fact_review", "no_trade_regret_score"]),
            "learning": lambda: self._module("learning", self._operator._learning_overview(), ["trade_reviews", "signal_performance", "engine_learning", "source_learning", "whale_learning", "ai_learning", "no_trade_learning", "model_adjustments"]),
            "memory": lambda: self._memory(),
            "market": lambda: self._market(),
            "opportunities": lambda: self._module("opportunities", self._operator._opportunities_overview(), ["opportunity_runs", "opportunity_scores_v2", "opportunity_signal_inputs", "opportunity_risk_flags"]),
            "capital": lambda: self._module("capital", self._operator._capital_overview(), ["capital_state_v2", "engine_budgets", "capital_allocations_v2", "capital_events"]),
            "execution": lambda: self._module("execution", self._operator._execution_overview(), ["orders_v2", "fills_v2", "execution_errors", "execution_quality"]),
            "exits": lambda: self._module("exits", self._operator._exit_overview(), ["exit_plans", "exit_intents", "exit_events", "exit_failures", "exit_quality"]),
            "news": lambda: self._module("news", self._operator._news_neuron_overview(), ["news_sources", "news_normalized_events", "news_market_links", "news_impact_scores"]),
            "social": lambda: self._module("social", self._operator._social_neuron_overview(), ["social_sources", "social_normalized_events", "social_hype_scores", "social_narratives"]),
            "whales": lambda: self._module("whales", self._operator._whale_neuron_overview(), ["whale_sources", "whale_events", "whale_profiles", "whale_market_scores", "whale_memory"]),
            "live-flow": lambda: self._live_flow(),
            "settings": lambda: self._settings(),
        }

    def _overview(self, limit: int) -> tuple[dict[str, object], list[str]]:
        fast = self._fast_overview_truth(limit)
        runtime = fast["runtime"]
        capital = fast["capital"]
        risk = fast["risk"]
        opportunities = fast["opportunities"]
        execution = fast["execution"]
        exits = fast["exits"]
        no_trade = fast["no_trade"]
        learning = fast["learning"]
        event_bus = fast["event_bus"]
        ai = fast["ai"]
        signals = fast["signals"]
        lineage = fast["signal_lineage"]
        brain_outputs = fast["brain_outputs"]
        coordinator = fast["coordinator"]
        impact_graph = fast["impact_graph"]
        thesis = fast["thesis"]
        neurons = fast["neurons"]
        summary = {
            "system_mode": runtime.get("current_mode"),
            "health": runtime.get("overall_runtime_health") or "DEGRADED",
            "current_balance": capital.get("total_capital"),
            "available_balance": capital.get("available_capital"),
            "locked_capital": capital.get("locked_capital"),
            "pnl_today": capital.get("daily_pnl_usd"),
            "pnl_by_engine": [],
            "risk_status": risk.get("risk_status"),
            "risk_governor_status": risk.get("governor_status"),
            "open_positions": risk.get("open_positions_count"),
            "top_opportunities": opportunities.get("top_opportunities") or opportunities.get("recent_opportunities") or [],
            "kill_switch": bool(risk.get("kill_switch_active") or runtime.get("kill_switch_active")),
            "ai_cost": ai.get("ai_cost_today"),
            "event_bus_health": event_bus.get("event_bus_health"),
            "signals_per_minute": signals.get("signals_per_minute"),
            "total_signals_24h": signals.get("total_signals_24h"),
            "unprocessed_signals": signals.get("unprocessed_signals"),
            "signal_lineage_bound_pct_24h": lineage.get("bound_pct_24h"),
            "unbound_signals_24h": lineage.get("unbound_signals_24h"),
            "total_brain_outputs_24h": brain_outputs.get("total_outputs_24h"),
            "active_brain_outputs": brain_outputs.get("active_outputs"),
            "brain_outputs_without_dependencies": brain_outputs.get("outputs_without_dependencies"),
            "coordinator_decisions_24h": coordinator.get("total_decisions_24h"),
            "coordinator_execution_allowed_count": coordinator.get("execution_allowed_count"),
            "impact_links_total": impact_graph.get("impact_links_total"),
            "impact_unlinked_signals": impact_graph.get("unlinked_signals"),
            "positions_with_thesis": impact_graph.get("positions_with_thesis"),
            "total_thesis_profiles": thesis.get("total_thesis_profiles"),
            "thesis_paper_ready": thesis.get("paper_ready"),
            "thesis_live_ready": thesis.get("live_ready"),
            "avg_thesis_completeness_score": thesis.get("avg_completeness_score"),
            "positions_without_thesis": thesis.get("positions_without_thesis"),
            "total_neurons": neurons.get("total_neurons"),
            "active_neurons": neurons.get("active_neurons"),
            "degraded_neurons": neurons.get("degraded_neurons"),
            "latest_update": self._latest_timestamp([runtime, capital, risk, opportunities, execution, exits, no_trade, event_bus, ai]),
            "learning_status": learning.get("learning_status"),
            "pending_reviews": learning.get("pending_reviews"),
            "live_certified": False,
            "operational_status": self._operational_status(risk, execution, exits, no_trade),
        }
        data = {
            "summary": summary,
            "runtime": runtime,
            "capital": capital,
            "risk": risk,
            "opportunities": opportunities,
            "execution": execution,
            "exits": exits,
            "no_trade": no_trade,
            "learning": learning,
            "event_bus": event_bus,
            "signals": signals,
            "signal_lineage": lineage,
            "brain_outputs": brain_outputs,
            "coordinator": coordinator,
            "impact_graph": impact_graph,
            "thesis": thesis,
            "neurons": neurons,
            "ai": ai,
        }
        return data, ["runtime_state", "service_health", "capital_state_v2", "risk_governor_state", "opportunity_scores_v2", "orders_v2", "exit_plans", "no_trade_log", "trade_reviews", "event_log", "neuron_signals", "neuron_registry", "neuron_health", "brain_outputs", "brain_output_dependencies", "brain_output_conflicts", "coordinator_decisions", "impact_links", "event_entities", "signal_market_links", "signal_position_links", "position_thesis_profiles", "position_thesis_validation_events"]

    def _fast_overview_truth(self, limit: int) -> dict[str, dict[str, object]]:
        if not self._factory.enabled:
            return {
                "runtime": {"status": "INSUFFICIENT_DATA", "current_mode": None},
                "capital": {"capital_status": "INSUFFICIENT_DATA"},
                "risk": {"risk_status": "INSUFFICIENT_DATA"},
                "opportunities": {"recent_opportunities": []},
                "execution": {"execution_status": "INSUFFICIENT_DATA"},
                "exits": {"exit_status": "INSUFFICIENT_DATA"},
                "no_trade": {"no_trade_status": "INSUFFICIENT_DATA"},
                "learning": {"learning_status": "INSUFFICIENT_DATA"},
                "event_bus": {"event_bus_health": "INSUFFICIENT_DATA"},
                "signals": {
                    "signal_status": "INSUFFICIENT_DATA",
                    "signals_per_minute": 0.0,
                    "total_signals_24h": 0,
                    "signals_by_neuron": [],
                    "latest_signals": [],
                    "stale_signals": [],
                    "unprocessed_signals": 0,
                },
                "signal_lineage": {
                    "status": "INSUFFICIENT_DATA",
                    "mock_data": False,
                    "total_signals_24h": 0,
                    "bound_signals_24h": 0,
                    "unbound_signals_24h": 0,
                    "bound_pct_24h": 0.0,
                    "signals_by_producer": [],
                    "signals_by_source": [],
                    "signals_without_correlation_id": 0,
                    "signals_without_raw_payload_ref": 0,
                    "latest_unbound_signals": [],
                },
                "brain_outputs": {
                    "status": "OK",
                    "mock_data": False,
                    "total_outputs_24h": 0,
                    "active_outputs": 0,
                    "expired_outputs": 0,
                    "outputs_by_brain": [],
                    "outputs_by_status": [],
                    "latest_outputs": [],
                    "recent_conflicts": [],
                    "outputs_without_dependencies": 0,
                    "signals_with_outputs": 0,
                },
                "coordinator": {
                    "status": "OK",
                    "mock_data": False,
                    "total_decisions_24h": 0,
                    "decisions_by_state": [],
                    "recent_decisions": [],
                    "recent_conflicts": [],
                    "conflicts_detected_24h": 0,
                    "no_trade_decisions_24h": 0,
                    "risk_blocked_24h": 0,
                    "review_required_24h": 0,
                    "execution_allowed_count": 0,
                    "decisions_requiring_governor": 0,
                    "blocked_actions_summary": [],
                },
                "impact_graph": {
                    "status": "OK",
                    "mock_data": False,
                    "entities_total": 0,
                    "signal_market_links_total": 0,
                    "signal_position_links_total": 0,
                    "impact_links_total": 0,
                    "unlinked_signals": 0,
                    "links_by_status": [],
                    "impacts_by_direction": [],
                    "cortex_action_hints": [],
                    "latest_impacts": [],
                    "positions_with_thesis": 0,
                    "signals_without_market_link": 0,
                },
                "thesis": {
                    "status": "OK",
                    "mock_data": False,
                    "total_thesis_profiles": 0,
                    "active_thesis_profiles": 0,
                    "draft_thesis_profiles": 0,
                    "needs_review": 0,
                    "invalidated": 0,
                    "paper_ready": 0,
                    "live_ready": 0,
                    "avg_completeness_score": 0.0,
                    "positions_without_thesis": 0,
                    "latest_thesis_profiles": [],
                    "missing_required_fields_summary": [],
                },
                "neurons": {
                    "status": "INSUFFICIENT_DATA",
                    "mock_data": False,
                    "total_neurons": 0,
                    "active_neurons": 0,
                    "partial_neurons": 0,
                    "disabled_neurons": 0,
                    "missing_neurons": 0,
                    "degraded_neurons": 0,
                    "stale_neurons": 0,
                    "signals_per_neuron": [],
                    "last_signal_by_neuron": [],
                    "neuron_errors": [],
                    "silent_expected_neurons": [],
                    "neurons": [],
                },
                "ai": {"ai_status": "INSUFFICIENT_DATA"},
            }
        runtime_health = HealthTruthService(connection_factory=self._factory).get_health_truth()
        with self._factory.connect() as conn:
            runtime_row = self._first_row(
                conn,
                "system_state",
                "SELECT current_mode, kill_switch_active, cooldown_active, attack_mode_active, updated_at FROM system_state ORDER BY updated_at DESC, id DESC LIMIT 1",
            )
            capital_row = self._first_row(
                conn,
                "capital_state_v2",
                "SELECT total_capital_usd, available_capital_usd, locked_capital_usd, daily_pnl_usd, created_at FROM capital_state_v2 ORDER BY created_at DESC, id DESC LIMIT 1",
            )
            risk_row = self._first_row(
                conn,
                "risk_governor_state",
                "SELECT governor_status, kill_switch_active, open_positions_count, updated_at FROM risk_governor_state ORDER BY updated_at DESC, id DESC LIMIT 1",
            )
            latest_events = self._count_latest(conn, "event_log", "stored_at")
            latest_service_health = self._count_latest(conn, "service_health", "updated_at")
            opportunities = self._recent_rows(
                conn,
                "opportunity_scores_v2",
                "SELECT market_id, opportunity_score, score_band, created_at FROM opportunity_scores_v2 ORDER BY created_at DESC, id DESC LIMIT %s",
                limit,
            )
            ai_cost = self._first_row(
                conn,
                "ai_cost_ledger",
                "SELECT COALESCE(SUM(estimated_cost), 0) AS ai_cost_today, MAX(created_at) AS latest_at FROM ai_cost_ledger WHERE created_at::date = CURRENT_DATE",
            )
            return {
                "runtime": {
                    "status": "OK" if runtime_row else "NO_DATA",
                    "current_mode": runtime_health.get("current_mode")
                    or (runtime_row.get("current_mode") if runtime_row else None),
                    "kill_switch_active": runtime_health.get("kill_switch_active")
                    if runtime_row
                    else None,
                    "cooldown_active": runtime_health.get("cooldown_active") if runtime_row else None,
                    "attack_mode_active": runtime_health.get("attack_mode_active")
                    if runtime_row
                    else None,
                    "overall_runtime_health": runtime_health.get("overall_status")
                    if runtime_row
                    else "NO_DATA",
                    "updated_at": self._latest_timestamp(
                        [
                            runtime_row.get("updated_at") if runtime_row else None,
                            latest_service_health.get("latest_at"),
                        ]
                    ),
                },
                "capital": {
                    "capital_status": "OK" if capital_row else "NO_DATA",
                    "total_capital": capital_row.get("total_capital_usd") if capital_row else None,
                    "available_capital": capital_row.get("available_capital_usd") if capital_row else None,
                    "locked_capital": capital_row.get("locked_capital_usd") if capital_row else None,
                    "daily_pnl_usd": capital_row.get("daily_pnl_usd") if capital_row else None,
                    "updated_at": capital_row.get("created_at") if capital_row else None,
                },
                "risk": {
                    "risk_status": risk_row.get("governor_status") if risk_row else "NO_DATA",
                    "governor_status": risk_row.get("governor_status") if risk_row else None,
                    "kill_switch_active": risk_row.get("kill_switch_active") if risk_row else None,
                    "open_positions_count": risk_row.get("open_positions_count") if risk_row else None,
                    "updated_at": risk_row.get("updated_at") if risk_row else None,
                },
                "opportunities": {
                    "opportunity_status": "OK" if opportunities else "NO_DATA",
                    "recent_opportunities": opportunities,
                },
                "execution": self._simple_count_status(conn, "orders_v2", "execution_status"),
                "exits": self._simple_count_status(conn, "exit_plans", "exit_status"),
                "no_trade": self._simple_count_status(conn, "no_trade_log", "no_trade_status"),
                "learning": self._simple_count_status(conn, "trade_reviews", "learning_status"),
                "event_bus": {
                    "event_bus_health": "OK" if latest_events["count"] > 0 else "NO_DATA",
                    "total_events": latest_events["count"],
                    "latest_event_time": latest_events["latest_at"],
                },
                "signals": self._signal_summary(limit),
                "signal_lineage": self._lineage_summary(limit),
                "brain_outputs": self._brain_output_summary(limit),
                "coordinator": self._coordinator_summary(limit),
                "impact_graph": self._impact_graph_summary(limit),
                "thesis": self._thesis_summary(limit),
                "neurons": self._neuron_summary(),
                "ai": {
                    "ai_status": "OK" if ai_cost else "NO_DATA",
                    "ai_cost_today": ai_cost.get("ai_cost_today") if ai_cost else None,
                    "updated_at": ai_cost.get("latest_at") if ai_cost else None,
                },
            }

    def _events(self, limit: int) -> tuple[dict[str, object], list[str]]:
        event_bus = self._operator._event_bus_overview()
        audit = self._safe("audit", lambda: self._operator.get_audit_views(limit=limit))
        return {"event_bus": event_bus, "audit": audit}, ["event_log", "event_consumers", "event_replay_jobs", "operator_control_actions", "alert_events"]

    def _signals(self, limit: int) -> tuple[dict[str, object], list[str]]:
        return {
            "signals": self._signal_summary(limit),
            "signal_lineage": self._lineage_summary(limit),
        }, ["neuron_signals", "neuron_signal_entities", "neuron_signal_evidence", "neuron_signal_bindings"]

    def _signal_lineage(self, limit: int) -> tuple[dict[str, object], list[str]]:
        return {"signal_lineage": self._lineage_summary(limit)}, ["neuron_signals", "neuron_signal_bindings", "neuron_producers", "source_status", "event_log"]

    def _brain_outputs(self, limit: int) -> tuple[dict[str, object], list[str]]:
        return {"brain_outputs": self._brain_output_summary(limit)}, ["brain_outputs", "brain_output_dependencies", "brain_output_conflicts", "neuron_signals"]

    def _coordinator(self, limit: int) -> tuple[dict[str, object], list[str]]:
        return {"coordinator": self._coordinator_summary(limit)}, ["coordinator_decisions", "coordinator_decision_inputs", "coordinator_decision_conflicts", "brain_outputs"]

    def _impact_graph(self, limit: int) -> tuple[dict[str, object], list[str]]:
        return {"impact_graph": self._impact_graph_summary(limit)}, ["event_entities", "entity_market_links", "signal_market_links", "signal_position_links", "position_thesis_profiles", "impact_links", "neuron_signals"]

    def _thesis(self, limit: int) -> tuple[dict[str, object], list[str]]:
        return {"thesis": self._thesis_summary(limit)}, ["position_thesis_profiles", "position_thesis_validation_events", "positions", "paper_positions", "shadow_positions"]

    def _neurons(self) -> tuple[dict[str, object], list[str]]:
        return {"neurons": self._neuron_summary()}, ["neuron_registry", "neuron_health", "neuron_signals", "source_status"]

    def _signal_summary(self, limit: int) -> dict[str, object]:
        summary = NeuronSignalService(connection_factory=self._factory).get_signal_summary(limit=limit)
        return {
            "signal_status": "OK" if summary["total_signals_24h"] > 0 else "NO_DATA",
            **summary,
        }

    def _lineage_summary(self, limit: int) -> dict[str, object]:
        return SignalLineageService(connection_factory=self._factory).get_lineage_summary(limit=limit)

    def _brain_output_summary(self, limit: int) -> dict[str, object]:
        return BrainOutputService(connection_factory=self._factory).get_brain_output_summary(limit=limit)

    def _coordinator_summary(self, limit: int) -> dict[str, object]:
        return BrainCoordinatorService(connection_factory=self._factory).get_coordinator_summary(limit=limit)

    def _impact_graph_summary(self, limit: int) -> dict[str, object]:
        return ImpactGraphService(connection_factory=self._factory).get_impact_graph_summary(limit=limit)

    def _thesis_summary(self, limit: int) -> dict[str, object]:
        return PositionThesisService(connection_factory=self._factory).get_thesis_summary(limit=limit)

    def _neuron_summary(self) -> dict[str, object]:
        return NeuronRegistryService(connection_factory=self._factory).get_neuron_mesh_summary()

    def _memory(self) -> tuple[dict[str, object], list[str]]:
        return {
            "market_memory": self._operator._market_memory_overview(),
            "no_trade": self._operator._no_trade_overview(),
            "learning": self._operator._learning_overview(),
            "whales": self._operator._whale_neuron_overview(),
            "rules": self._operator._rules_neuron_overview(),
        }, ["market_memory", "market_family_memory", "engine_performance_memory", "source_reliability_memory", "whale_memory", "slippage_memory", "rules_risk_memory", "no_trade_log", "trade_reviews", "model_adjustments"]

    def _market(self) -> tuple[dict[str, object], list[str]]:
        return self._fast_market_truth(), ["markets_v2", "market_snapshots_v2", "orderbook_snapshots", "liquidity_snapshots", "market_technical_signals"]

    def _fast_market_truth(self) -> dict[str, object]:
        if not self._factory.enabled:
            return {
                "data_foundation": {"status": "INSUFFICIENT_DATA"},
                "technical": {"technical_status": "INSUFFICIENT_DATA"},
                "ranking": {"status": "INSUFFICIENT_DATA", "recent": []},
            }
        with self._factory.connect() as conn:
            market_counts = self._first_row(
                conn,
                "markets_v2",
                """
                SELECT
                    COUNT(*) AS total_markets,
                    COUNT(*) FILTER (WHERE active = true) AS active_markets,
                    COUNT(*) FILTER (WHERE accepting_orders = true AND closed = false AND archived = false) AS tradable_markets,
                    MAX(updated_at) AS latest_at
                FROM markets_v2
                """,
            ) or {}
            snapshot_counts = self._first_row(
                conn,
                "market_snapshots_v2",
                """
                SELECT
                    COUNT(*) AS total_snapshots,
                    COUNT(*) FILTER (WHERE stale = true) AS stale_snapshots,
                    AVG(data_completeness_score) AS average_data_completeness,
                    MAX(snapshot_at) AS latest_at
                FROM market_snapshots_v2
                """,
            ) or {}
            orderbook_counts = self._count_latest(conn, "orderbook_snapshots", "snapshot_at")
            liquidity_counts = self._count_latest(conn, "liquidity_snapshots", "snapshot_at")
            technical_counts = self._first_row(
                conn,
                "market_technical_signals",
                """
                SELECT
                    COUNT(*) AS signal_count,
                    COUNT(*) FILTER (WHERE stale = true) AS stale_signal_count,
                    AVG(technical_score) AS average_technical_score,
                    MAX(created_at) AS latest_at
                FROM market_technical_signals
                """,
            ) or {}
            recent_technical = self._recent_rows(
                conn,
                "market_technical_signals",
                """
                SELECT market_id, market_slug, technical_score, trend_direction, stale, created_at
                FROM market_technical_signals
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                8,
            )
            return {
                "data_foundation": {
                    "status": "OK" if market_counts.get("total_markets") else "NO_DATA",
                    "total_markets": int(market_counts.get("total_markets") or 0),
                    "active_markets": int(market_counts.get("active_markets") or 0),
                    "tradable_markets": int(market_counts.get("tradable_markets") or 0),
                    "latest_market_update": market_counts.get("latest_at"),
                    "total_snapshots": int(snapshot_counts.get("total_snapshots") or 0),
                    "stale_snapshots": int(snapshot_counts.get("stale_snapshots") or 0),
                    "average_data_completeness": snapshot_counts.get("average_data_completeness"),
                    "latest_snapshot_at": snapshot_counts.get("latest_at"),
                },
                "orderbooks": {
                    "status": "OK" if orderbook_counts["count"] > 0 else "NO_DATA",
                    "snapshot_count": orderbook_counts["count"],
                    "latest_snapshot_at": orderbook_counts["latest_at"],
                },
                "liquidity": {
                    "status": "OK" if liquidity_counts["count"] > 0 else "NO_DATA",
                    "snapshot_count": liquidity_counts["count"],
                    "latest_snapshot_at": liquidity_counts["latest_at"],
                },
                "technical": {
                    "technical_status": "OK" if technical_counts.get("signal_count") else "NO_DATA",
                    "signal_count": int(technical_counts.get("signal_count") or 0),
                    "stale_signal_count": int(technical_counts.get("stale_signal_count") or 0),
                    "average_technical_score": technical_counts.get("average_technical_score"),
                    "latest_signal_at": technical_counts.get("latest_at"),
                },
                "ranking": {
                    "status": "OK" if recent_technical else "NO_DATA",
                    "recent": recent_technical,
                },
            }

    def _live_flow(self) -> tuple[dict[str, object], list[str]]:
        modules = [
            ("Market data", self._operator._data_foundation_overview()),
            ("News", self._operator._news_neuron_overview()),
            ("Social", self._operator._social_neuron_overview()),
            ("Whales", self._operator._whale_neuron_overview()),
            ("Technical neurons", self._operator._market_technical_overview()),
            ("Memory", self._operator._market_memory_overview()),
            ("Brains", self._operator._brains_overview()),
            ("Opportunities", self._operator._opportunities_overview()),
            ("Strategy", self._operator._strategy_overview()),
            ("Capital", self._operator._capital_overview()),
            ("Risk", self._operator._risk_overview()),
            ("Execution", self._operator._execution_overview()),
            ("Exits", self._operator._exit_overview()),
            ("No-Trade", self._operator._no_trade_overview()),
            ("Learning", self._operator._learning_overview()),
            ("Events", self._operator._event_bus_overview()),
        ]
        nodes = []
        for label, payload in modules:
            status = self._infer_status(payload)
            nodes.append(
                {
                    "label": label,
                    "status": status,
                    "latest_at": self._latest_timestamp([payload]),
                    "stale": status in {"STALE", "NO_DATA", "ERROR", "DEGRADED"},
                    "pulse": status in {"OK", "HEALTHY"} and self._latest_timestamp([payload]) is not None,
                    "data": payload,
                }
            )
        return {"nodes": nodes}, ["event_log", "markets_v2", "opportunity_scores_v2", "strategy_routes_v2", "capital_allocations_v2", "risk_gate_decisions", "orders_v2", "exit_plans", "no_trade_log"]

    def _settings(self) -> tuple[dict[str, object], list[str]]:
        return {
            "theme": "polybot-dark-cockpit",
            "refresh_interval_seconds": 30,
            "density": "operator",
            "default_landing_page": "overview",
            "stale_threshold_seconds": int(_STALE_AFTER.total_seconds()),
            "advanced_controls": {
                "policy": "locked_reason_confirm_audit_required",
                "unlock_required": True,
                "reason_required": True,
                "confirmation_required": True,
                "actor_required": True,
                "dangerous_one_click_controls": False,
                "available_controls": [],
                "not_available_yet": ["kill", "pause", "resume", "mode_change", "dlq_replay", "manual_cooldown", "disable_engine", "manual_override"],
                "note": "Dashboard V2 exposes no write/control API in this phase; existing backend controls remain outside this cockpit unless a safe audited endpoint already exists.",
            },
            "live_certified": False,
        }, ["settings", "operator_control_actions"]

    def _module(self, name: str, payload: dict[str, object], tables: list[str]) -> tuple[dict[str, object], list[str]]:
        return {name: payload}, tables

    def _table_exists(self, conn: Any, table: str) -> bool:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
        return bool(row and row["table_name"])

    def _first_row(self, conn: Any, table: str, query: str) -> dict[str, object] | None:
        if not self._table_exists(conn, table):
            return None
        row = conn.execute(query).fetchone()
        return dict(row) if row else None

    def _recent_rows(self, conn: Any, table: str, query: str, limit: int) -> list[dict[str, object]]:
        if not self._table_exists(conn, table):
            return []
        return [dict(row) for row in conn.execute(query, (limit,)).fetchall()]

    def _count_latest(self, conn: Any, table: str, timestamp_column: str) -> dict[str, object]:
        if not self._table_exists(conn, table):
            return {"count": 0, "latest_at": None}
        row = conn.execute(f"SELECT COUNT(*) AS count, MAX({timestamp_column}) AS latest_at FROM {table}").fetchone()
        return {"count": int(row["count"] or 0), "latest_at": row["latest_at"]}

    def _simple_count_status(self, conn: Any, table: str, status_key: str) -> dict[str, object]:
        counts = self._count_latest(conn, table, "created_at")
        return {
            status_key: "OK" if counts["count"] > 0 else "NO_DATA",
            "count": counts["count"],
            "latest_at": counts["latest_at"],
        }

    def _safe(self, name: str, fn: Callable[[], dict[str, object]]) -> dict[str, object]:
        try:
            return fn()
        except Exception as exc:
            return {"status": "ERROR", "errors": [f"{name}:{exc}"]}

    def _runtime_overview(self) -> dict[str, object]:
        runtime_health = HealthTruthService(connection_factory=self._factory).get_health_truth()
        transition = runtime_health.get("last_mode_transition") or {}
        if not isinstance(transition, dict):
            transition = {}
        return {
            "current_mode": runtime_health.get("current_mode"),
            "kill_switch_active": runtime_health.get("kill_switch_active"),
            "cooldown_active": runtime_health.get("cooldown_active"),
            "attack_mode_active": runtime_health.get("attack_mode_active"),
            "last_mode_change": transition.get("created_at"),
            "last_reason": transition.get("reason"),
            "last_actor": transition.get("actor"),
            "overall_runtime_health": runtime_health.get("overall_status"),
            "active_cycle": runtime_health.get("active_cycle"),
            "service_count": len(runtime_health.get("services") or []),
            "degraded_services": len(runtime_health.get("stale_services") or []),
        }

    def _safe_overview_key(self, key: str, limit: int) -> dict[str, object]:
        try:
            overview = self._operator.get_dashboard_overview(limit=limit)
            value = overview.get(key)
            return value if isinstance(value, dict) else {}
        except Exception as exc:
            return {"status": "ERROR", "errors": [f"{key}:{exc}"]}

    def _envelope(
        self,
        *,
        page: str,
        data: dict[str, object],
        generated_at: datetime,
        errors: list[str],
        source_tables: list[str],
    ) -> dict[str, object]:
        latest_at = self._latest_timestamp([data])
        status = "ERROR" if errors else self._infer_status(data)
        stale, stale_reason = self._stale_state(status, latest_at, generated_at)
        if stale and status in {"OK", "HEALTHY"}:
            status = "STALE"
        return {
            "status": status,
            "updated_at": latest_at or generated_at.isoformat(),
            "stale": stale,
            "stale_reason": stale_reason,
            "data_source": {
                "type": "postgres_runtime_truth",
                "service": "OperatorDashboardQueryService",
                "tables": source_tables,
                "mock_data": False,
            },
            "data_confidence": self._data_confidence(status, stale, errors, data),
            "errors": errors,
            "page": page,
            "data": self._json_safe(data),
        }

    def _stale_state(self, status: str, latest_at: str | None, generated_at: datetime) -> tuple[bool, str | None]:
        if status == "ERROR":
            return True, "dashboard query returned errors"
        if status in {"NO_DATA", "DISABLED", "EMPTY", "INSUFFICIENT_DATA"}:
            return True, "source has no usable rows or is insufficient"
        if latest_at is None:
            return True, "no timestamped source rows available"
        try:
            parsed = datetime.fromisoformat(latest_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
        except ValueError:
            return True, "latest source timestamp could not be parsed"
        if generated_at - parsed > _STALE_AFTER:
            return True, f"latest source row older than {int(_STALE_AFTER.total_seconds())} seconds"
        return False, None

    def _data_confidence(self, status: str, stale: bool, errors: list[str], data: dict[str, object]) -> float:
        if errors or status == "ERROR":
            return 0.0
        if status in {"NO_DATA", "DISABLED", "EMPTY", "INSUFFICIENT_DATA"}:
            return 0.35
        if stale:
            return 0.55
        if not data:
            return 0.25
        return 0.9

    def _infer_status(self, data: dict[str, object]) -> str:
        statuses: list[str] = []
        self._collect_statuses(data, statuses)
        if any(status == "ERROR" for status in statuses):
            return "ERROR"
        if any(status == "DEGRADED" for status in statuses):
            return "DEGRADED"
        if statuses and all(status in _NO_DATA_STATUSES for status in statuses):
            return "NO_DATA"
        if any(status in {"OK", "HEALTHY", "RUNNING", "RECORDED"} for status in statuses):
            return "OK"
        if self._has_rows(data):
            return "OK"
        return "NO_DATA"

    def _collect_statuses(self, value: Any, statuses: list[str]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("status") or key in {"status", "health", "event_bus_health", "risk_status", "capital_status", "execution_status", "exit_status", "no_trade_status"}:
                    if isinstance(item, str):
                        statuses.append(item.upper())
                self._collect_statuses(item, statuses)
        elif isinstance(value, list):
            for item in value:
                self._collect_statuses(item, statuses)

    def _collect_errors(self, value: Any) -> list[str]:
        errors: list[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "errors" and isinstance(item, list):
                    errors.extend(str(error) for error in item if error)
                else:
                    errors.extend(self._collect_errors(item))
        elif isinstance(value, list):
            for item in value:
                errors.extend(self._collect_errors(item))
        return errors

    def _latest_timestamp(self, values: list[Any]) -> str | None:
        timestamps: list[datetime] = []
        for value in values:
            parsed = self._parse_datetime(value)
            if parsed is not None:
                timestamps.append(parsed)
            else:
                self._collect_timestamps(value, timestamps)
        if not timestamps:
            return None
        return max(timestamps).isoformat()

    def _collect_timestamps(self, value: Any, timestamps: list[datetime]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_at") or key in {"created_at", "updated_at", "latest_update", "latest_score_ts", "latest_route_ts"}:
                    parsed = self._parse_datetime(item)
                    if parsed is not None:
                        timestamps.append(parsed)
                self._collect_timestamps(item, timestamps)
        elif isinstance(value, list):
            for item in value:
                self._collect_timestamps(item, timestamps)

    def _parse_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                return None
        return None

    def _has_rows(self, value: Any) -> bool:
        if isinstance(value, dict):
            return any(self._has_rows(item) for item in value.values())
        if isinstance(value, list):
            return len(value) > 0
        return False

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    def _operational_status(
        self,
        risk: dict[str, object],
        execution: dict[str, object],
        exits: dict[str, object],
        no_trade: dict[str, object],
    ) -> str:
        if risk.get("kill_switch_active"):
            return "KILL_ACTIVE"
        if risk.get("risk_status") == "ERROR" or execution.get("execution_status") == "ERROR":
            return "DEGRADED"
        if exits.get("orphan_orders_count"):
            return "EXIT_ATTENTION_REQUIRED"
        if no_trade.get("high_regret_count"):
            return "REVIEW_NO_TRADE_REGRET"
        return "SAFE_TO_OBSERVE"
