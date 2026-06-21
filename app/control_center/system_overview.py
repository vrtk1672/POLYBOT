from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.control_center.paper_simulation import PaperSimulationControlService
from app.control_center.runtime_supervisor import RuntimeSupervisorService
from app.control_center.source_refresh_status import SourceRefreshStatusService
from app.db.connection import DatabaseConnectionFactory
from app.runtime.state_governor import StateGovernor
from app.services.system_power import SystemPowerService


class SystemOverviewService:
    """Read-only unified operator status for the autonomous runtime.

    This surface intentionally does not run refreshes, create candidates, or
    mutate execution state. It summarizes whether POLYBOT is OFF, DATA_ONLY, or
    effectively running with the PAPER execution adapter enabled.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        governor: StateGovernor | None = None,
        system_power: SystemPowerService | None = None,
        paper_simulation: PaperSimulationControlService | None = None,
        runtime_supervisor: RuntimeSupervisorService | None = None,
        source_refresh: SourceRefreshStatusService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._system_power = system_power or SystemPowerService(connection_factory=self._factory)
        self._paper_simulation = paper_simulation or PaperSimulationControlService(connection_factory=self._factory, governor=self._governor)
        self._runtime_supervisor = runtime_supervisor or RuntimeSupervisorService(governor=self._governor)
        self._source_refresh = source_refresh or SourceRefreshStatusService(connection_factory=self._factory)

    def get_overview(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        power = self._safe_power()
        runtime = self._safe_runtime_state()
        paper = self._safe_paper_status()
        supervisor = self._safe_supervisor()
        source_refresh = self._safe_source_refresh()
        db = self._database_snapshot()
        execution_mode = derive_execution_mode(
            system_power=str(power.get("power") or power.get("system_power") or "OFF"),
            paper_simulation_enabled=bool(paper.get("enabled")),
            runtime_mode=str(runtime.get("current_mode") or power.get("current_mode") or ""),
        )
        live_orders = _int(db["execution"].get("live_orders"))
        shadow_orders = _int(db["execution"].get("shadow_orders"))
        live_adapter_state = "BLOCKED" if live_orders == 0 else "UNEXPECTED_ACTIVITY"
        paper_adapter_state = "ENABLED" if execution_mode == "PAPER" else "DISABLED"
        source_refresh_state = (
            source_refresh.get("source_refresh_orchestrator_state")
            or source_refresh.get("status")
            or supervisor.get("source_refresh_orchestrator_state")
            or "UNKNOWN"
        )
        disconnected = _disconnected_services(
            power,
            supervisor,
            {**source_refresh, "source_refresh_orchestrator_state": source_refresh_state},
            db,
        )
        errors = _unique(
            [
                *runtime.get("errors", []),
                *power.get("errors", []),
                *paper.get("errors", []),
                *supervisor.get("errors", []),
                *source_refresh.get("errors", []),
                *db.get("errors", []),
            ]
        )
        warnings = _unique(
            [
                *runtime.get("warnings", []),
                *power.get("warnings", []),
                *paper.get("warnings", []),
                *supervisor.get("warnings", []),
                *source_refresh.get("warnings", []),
                *db.get("warnings", []),
                *disconnected,
            ]
        )
        next_action = _next_action(
            system_power=str(power.get("power") or "OFF"),
            execution_mode=execution_mode,
            markets_total=_int(db["market_universe"].get("total")),
            open_positions=_int(db["execution"].get("open_paper_positions")),
            blockers=db["decisions"].get("top_blockers") or warnings,
        )
        return _json_safe(
            {
                "status": "REAL" if db["database"]["enabled"] else "PARTIAL",
                "source": "control_center:system_overview",
                "generated_at": generated_at,
                "system_power": power.get("power") or power.get("system_power") or "OFF",
                "runtime_state": runtime.get("current_mode") or power.get("current_mode") or "UNKNOWN",
                "execution_mode": execution_mode,
                "paper_adapter_state": paper_adapter_state,
                "live_adapter_state": live_adapter_state,
                "supervisor_state": supervisor.get("supervisor_status") or "UNKNOWN",
                "source_refresh_state": source_refresh_state,
                "database": db["database"],
                "market_universe": db["market_universe"],
                "sources_events": db["sources_events"],
                "triggers": db["triggers"],
                "candidates": db["candidates"],
                "decisions": db["decisions"],
                "execution": {
                    **db["execution"],
                    "paper_adapter_state": paper_adapter_state,
                    "live_adapter_state": live_adapter_state,
                    "execution_mode": execution_mode,
                },
                "pnl": db["pnl"],
                "paper_session": db.get("paper_session", {}),
                "learning": db["learning"],
                "ai_mesh_intelligence": db.get("ai_mesh_intelligence", {}),
                "runtime_truth": db.get("runtime_truth", {}),
                "runtime": runtime,
                "paper_simulation": paper,
                "supervisor": supervisor,
                "source_refresh": source_refresh,
                "errors": errors,
                "warnings": warnings,
                "stale_components": db["stale_components"],
                "disconnected_services": disconnected,
                "next_recommended_action": next_action,
                "safety": {
                    "paper_mode_is_execution_adapter_only": True,
                    "analysis_logic_paper_specific": False,
                    "live_adapter_disabled": live_adapter_state == "BLOCKED",
                    "shadow_adapter_disabled": _int(db["execution"].get("shadow_orders")) == 0,
                    "real_orders_created": _int(db["execution"].get("real_orders")),
                    "live_orders_created": live_orders,
                    "shadow_orders_created": shadow_orders,
                },
            }
        )

    def _safe_power(self) -> dict[str, Any]:
        try:
            payload = self._system_power.get_dashboard_summary()
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            return {"power": "OFF", "errors": [f"{type(exc).__name__}: {exc}"]}

    def _safe_runtime_state(self) -> dict[str, Any]:
        try:
            state = self._governor.get_current_state()
            permissions = self._governor.get_permissions()
            return {
                "current_mode": getattr(getattr(state, "current_mode", None), "value", str(getattr(state, "current_mode", "UNKNOWN"))),
                "system_power": getattr(getattr(state, "system_power", None), "value", str(getattr(state, "system_power", "UNKNOWN"))),
                "kill_switch_active": bool(getattr(state, "kill_switch_active", False)),
                "cooldown_active": bool(getattr(state, "cooldown_active", False)),
                "permissions": permissions.to_dict() if hasattr(permissions, "to_dict") else {},
                "warnings": [],
                "errors": [],
            }
        except Exception as exc:
            return {"current_mode": "UNKNOWN", "warnings": ["Runtime State Governor unavailable."], "errors": [f"{type(exc).__name__}: {exc}"]}

    def _safe_paper_status(self) -> dict[str, Any]:
        try:
            record = self._paper_simulation.status_record(include_paper_truth=False)
            return record.to_action_result() if hasattr(record, "to_action_result") else dict(record)
        except Exception as exc:
            return {"enabled": False, "status": "ERROR", "warnings": [], "errors": [f"{type(exc).__name__}: {exc}"]}

    def _safe_supervisor(self) -> dict[str, Any]:
        try:
            payload = self._runtime_supervisor.status()
            data = payload.get("data") if isinstance(payload, dict) else {}
            if isinstance(data, dict):
                return {**data, "warnings": payload.get("warnings") or data.get("warnings") or [], "errors": payload.get("errors") or data.get("errors") or []}
            return {}
        except Exception as exc:
            return {"supervisor_status": "UNKNOWN", "warnings": [], "errors": [f"{type(exc).__name__}: {exc}"]}

    def _safe_source_refresh(self) -> dict[str, Any]:
        try:
            payload = self._source_refresh.get_status()
            data = payload.get("data") if isinstance(payload, dict) else payload
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            return {"status": "UNKNOWN", "warnings": [], "errors": [f"{type(exc).__name__}: {exc}"]}

    def _database_snapshot(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty_db_snapshot(warning="POLYBOT_DATABASE_URL is not configured for this process.")
        try:
            with self._factory.connect() as conn:
                tables = _table_cache(conn)
                return {
                    "database": {"enabled": True, "status": "OK"},
                    "market_universe": _market_universe(conn, tables),
                    "sources_events": _sources_events(conn, tables),
                    "triggers": _triggers(conn, tables),
                    "candidates": _candidates(conn, tables),
                    "decisions": _decisions(conn, tables),
                    "execution": _execution(conn, tables),
                    "pnl": _pnl(conn, tables),
                    "paper_session": _paper_session_summary(conn, tables),
                    "learning": _learning(conn, tables),
                    "ai_mesh_intelligence": _ai_mesh_intelligence(conn, tables),
                    "runtime_truth": _runtime_truth(conn, tables),
                    "stale_components": _stale_components(conn, tables),
                    "warnings": [],
                    "errors": [],
                }
        except Exception as exc:
            snapshot = _empty_db_snapshot(warning="Database snapshot failed.")
            snapshot["database"] = {"enabled": True, "status": "ERROR"}
            snapshot["errors"] = [f"{type(exc).__name__}: {exc}"]
            return snapshot


def derive_execution_mode(*, system_power: str, paper_simulation_enabled: bool, runtime_mode: str | None = None) -> str:
    if str(system_power or "").upper() != "ON":
        return "DISABLED"
    if str(runtime_mode or "").upper() == "PAPER":
        return "PAPER"
    if paper_simulation_enabled:
        return "PAPER"
    return "DATA_ONLY"


def _empty_db_snapshot(*, warning: str) -> dict[str, Any]:
    return {
        "database": {"enabled": False, "status": "DATABASE_UNAVAILABLE"},
        "market_universe": _zero_market_universe(),
        "sources_events": {"recent_events": 0, "linked_events": 0, "unlinked_events": 0, "total_events": 0},
        "triggers": {"total": 0, "by_type": {}, "eligible": 0, "watch": 0, "blocked": 0},
        "candidates": {"seeds_generated": 0, "yes": 0, "no": 0, "side_unknown": 0, "mesh_reviewed": 0},
        "decisions": {"paper_ready_decisions": 0, "blocked_decisions": 0, "watch_decisions": 0, "top_blockers": []},
        "execution": _zero_execution(),
        "pnl": {"realized": 0.0, "unrealized": 0.0, "daily": 0.0, "status": "UNKNOWN"},
        "paper_session": {},
        "learning": {"closed_paper_trades": 0, "winning_trades": 0, "losing_trades": 0, "thesis_outcomes": 0},
        "ai_mesh_intelligence": _zero_ai_mesh_intelligence(),
        "stale_components": [],
        "warnings": [warning],
        "errors": [],
    }


def _zero_market_universe() -> dict[str, Any]:
    return {
        "total": 0,
        "active": 0,
        "closed": 0,
        "resolved": 0,
        "token_verified": 0,
        "unresolved": 0,
        "stale": 0,
        "priority": {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "DORMANT": 0, "ARCHIVED": 0},
        "watchlist_priority": {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "DORMANT": 0, "ARCHIVED": 0},
    }


def _zero_execution() -> dict[str, Any]:
    return {
        "paper_intents": 0,
        "paper_orders": 0,
        "paper_fills": 0,
        "paper_positions": 0,
        "open_paper_positions": 0,
        "live_orders": 0,
        "shadow_orders": 0,
        "real_orders": 0,
        "canonical_positions": 0,
        "execution_candidates": 0,
    }


def _market_universe(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "market_universe_memory" not in tables:
        return _zero_market_universe()
    cols = tables["market_universe_memory"]
    priority_col = "research_priority" if "research_priority" in cols else None
    priority = {band: 0 for band in ("HIGH", "MEDIUM", "LOW", "DORMANT", "ARCHIVED")}
    if priority_col:
        priority.update(_group_counts(conn, "market_universe_memory", priority_col))
    watchlist_priority = {band: 0 for band in ("HIGH", "MEDIUM", "LOW", "DORMANT", "ARCHIVED")}
    if "research_priority_watchlist" in tables and "priority_band" in tables["research_priority_watchlist"]:
        watchlist_priority.update(_group_counts(conn, "research_priority_watchlist", "priority_band"))
    return {
        "total": _count(conn, "market_universe_memory"),
        "active": _count_where(conn, "market_universe_memory", "status='ACTIVE'") if "status" in cols else _count_where(conn, "market_universe_memory", "active IS TRUE"),
        "closed": _count_where(conn, "market_universe_memory", "closed IS TRUE") if "closed" in cols else 0,
        "resolved": _count_where(conn, "market_universe_memory", "resolved IS TRUE") if "resolved" in cols else 0,
        "token_verified": _count_where(conn, "market_universe_memory", "token_verification_state='TOKENS_VERIFIED'") if "token_verification_state" in cols else 0,
        "unresolved": _count_where(conn, "market_universe_memory", "identity_verification_state='UNRESOLVED'") if "identity_verification_state" in cols else 0,
        "stale": _count_where(conn, "market_universe_memory", "freshness_state<>'FRESH'") if "freshness_state" in cols else 0,
        "priority": priority,
        "watchlist_priority": watchlist_priority,
    }


def _sources_events(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "source_event_memory" not in tables:
        return {"recent_events": 0, "linked_events": 0, "unlinked_events": 0, "total_events": 0}
    event_cols = tables["source_event_memory"]
    link_cols = tables.get("event_to_market_recall", set())
    total = _count(conn, "source_event_memory")
    time_col = "event_timestamp" if "event_timestamp" in event_cols else "created_at" if "created_at" in event_cols else None
    recent = _count_where(conn, "source_event_memory", f"{time_col} >= now() - interval '72 hours'") if time_col else 0
    if "event_to_market_recall" in tables and "source_event_id" in link_cols:
        linked = conn.execute(
            """
            SELECT COUNT(DISTINCT sem.source_event_id) AS count
            FROM source_event_memory sem
            JOIN event_to_market_recall emr ON emr.source_event_id=sem.source_event_id
            WHERE COALESCE(emr.link_type, '') <> 'NO_LINK'
            """
        ).fetchone()["count"]
    else:
        linked = 0
    return {"recent_events": _int(recent), "linked_events": _int(linked), "unlinked_events": max(0, _int(total) - _int(linked)), "total_events": _int(total)}


def _triggers(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "multi_trigger_candidate_triggers" not in tables:
        return {"total": 0, "by_type": {}, "eligible": 0, "watch": 0, "blocked": 0}
    cols = tables["multi_trigger_candidate_triggers"]
    by_type = _group_counts(conn, "multi_trigger_candidate_triggers", "trigger_type") if "trigger_type" in cols else {}
    state_col = "seed_generation_state" if "seed_generation_state" in cols else None
    return {
        "total": _count(conn, "multi_trigger_candidate_triggers"),
        "by_type": by_type,
        "eligible": _count_where(conn, "multi_trigger_candidate_triggers", f"{state_col}='ELIGIBLE'") if state_col else 0,
        "watch": _count_where(conn, "multi_trigger_candidate_triggers", f"{state_col}='WATCH_ONLY'") if state_col else 0,
        "blocked": _count_where(conn, "multi_trigger_candidate_triggers", f"{state_col}='BLOCKED'") if state_col else 0,
    }


def _candidates(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "proactive_candidate_seeds" not in tables:
        return {"seeds_generated": 0, "yes": 0, "no": 0, "side_unknown": 0, "mesh_reviewed": 0}
    cols = tables["proactive_candidate_seeds"]
    mesh_reviewed = 0
    if "proactive_seed_mesh_results" in tables:
        result_cols = tables["proactive_seed_mesh_results"]
        if "result_state" in result_cols:
            mesh_reviewed = _count_where(conn, "proactive_seed_mesh_results", "result_state IN ('MESH_DATA_ONLY_COMPLETED','MESH_COMPLETED','PARTIAL')")
        else:
            mesh_reviewed = _count(conn, "proactive_seed_mesh_results")
    return {
        "seeds_generated": _count(conn, "proactive_candidate_seeds"),
        "yes": _count_where(conn, "proactive_candidate_seeds", "side='YES'") if "side" in cols else 0,
        "no": _count_where(conn, "proactive_candidate_seeds", "side='NO'") if "side" in cols else 0,
        "side_unknown": _count_where(conn, "proactive_candidate_seeds", "side IN ('SIDE_UNKNOWN','UNKNOWN')") if "side" in cols else 0,
        "mesh_reviewed": mesh_reviewed,
    }


def _decisions(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    paper_ready = 0
    blocked = 0
    watch = 0
    blockers: list[str] = []
    runtime_total = 0
    runtime_enter = 0
    runtime_blocked = 0
    runtime_watch = 0
    runtime_top: list[dict[str, Any]] = []
    runtime_top_unique: list[dict[str, Any]] = []
    runtime_by_market: dict[str, int] = {}
    runtime_by_side: dict[str, int] = {}
    runtime_by_trigger_family: dict[str, int] = {}
    duplicate_by_market_side: list[str] = []
    unique_market_count = 0
    unique_side_count = 0
    unique_market_side_count = 0
    duplicate_suppressed_count = 0
    concentration_score = 0.0
    stale_orderbook_blocked = 0
    last_mile_refresh_attempts = 0
    last_mile_refresh_success = 0
    last_mile_refresh_failed = 0
    stale_cleared_count = 0
    stale_remaining_count = 0
    policy_state_counts: dict[str, int] = {}
    policy_by_market: dict[str, int] = {}
    policy_by_side: dict[str, int] = {}
    top_non_dominant_policy_blockers: list[dict[str, Any]] = []
    diversity_bottleneck_stage = "UNKNOWN"
    funnel_unique_pairs: dict[str, int] = {}
    if "paper_runtime_decisions" in tables:
        current_predicate = "is_current_batch IS TRUE" if "is_current_batch" in tables["paper_runtime_decisions"] else "true"
        runtime_total = _count_where(conn, "paper_runtime_decisions", current_predicate)
        runtime_enter = _count_where(conn, "paper_runtime_decisions", f"{current_predicate} AND decision='ENTER' AND paper_enter_allowed IS TRUE")
        runtime_blocked = _count_where(conn, "paper_runtime_decisions", f"{current_predicate} AND decision='BLOCK'")
        runtime_watch = _count_where(conn, "paper_runtime_decisions", f"{current_predicate} AND decision='WATCH'")
        blockers = _json_text_counter(conn, "paper_runtime_decisions", "blockers_json", limit=8, predicate=current_predicate) if "blockers_json" in tables["paper_runtime_decisions"] else []
        runtime_top = [
            _json_safe(dict(row))
            for row in conn.execute(
                f"""
                SELECT decision_id, market_id, side, opportunity_score, decision,
                       paper_enter_allowed, blockers_json, warnings_json,
                       diversity_score, duplicate_suppressed_count,
                       orderbook_snapshot_id AS selected_orderbook_snapshot_id,
                       orderbook_age_seconds, orderbook_ttl_seconds,
                       last_mile_refresh_attempted,
                       last_mile_refresh_state,
                       last_mile_refresh_error,
                       post_refresh_orderbook_state,
                       updated_at
                FROM paper_runtime_decisions
                WHERE {current_predicate}
                ORDER BY
                    CASE decision WHEN 'ENTER' THEN 0 WHEN 'WATCH' THEN 1 ELSE 2 END,
                    diversity_score DESC,
                    opportunity_score DESC,
                    updated_at DESC,
                    id DESC
                LIMIT 8
                """
            ).fetchall()
        ]
        runtime_top_unique = [
            _json_safe(dict(row))
            for row in conn.execute(
                f"""
                SELECT DISTINCT ON (market_id, side)
                       decision_id, market_id, side, opportunity_score, decision,
                       paper_enter_allowed, blockers_json, warnings_json,
                       diversity_score, duplicate_suppressed_count,
                       orderbook_snapshot_id AS selected_orderbook_snapshot_id,
                       orderbook_age_seconds, orderbook_ttl_seconds,
                       last_mile_refresh_attempted,
                       last_mile_refresh_state,
                       last_mile_refresh_error,
                       post_refresh_orderbook_state,
                       updated_at
                FROM paper_runtime_decisions
                WHERE {current_predicate}
                ORDER BY market_id, side, diversity_score DESC, opportunity_score DESC, updated_at DESC, id DESC
                LIMIT 20
                """
            ).fetchall()
        ]
        runtime_by_market = _group_counts_where(conn, "paper_runtime_decisions", "market_id", current_predicate, limit=12)
        runtime_by_side = _group_counts_where(conn, "paper_runtime_decisions", "side", current_predicate, limit=8)
        if "evidence" in tables["paper_runtime_decisions"]:
            runtime_by_trigger_family = {
                str(row["key"] or "UNKNOWN"): _int(row["count"])
                for row in conn.execute(
                    f"""
                    SELECT COALESCE(evidence->'diversity'->>'trigger_type', evidence->'diversity'->>'seed_type', 'UNKNOWN') AS key,
                           COUNT(*) AS count
                    FROM paper_runtime_decisions
                    WHERE {current_predicate}
                    GROUP BY key
                    ORDER BY count DESC, key
                    LIMIT 12
                    """
                ).fetchall()
            }
        duplicate_by_market_side = [
            f"{row['market_id']} {row['side']}: {row['count']}"
            for row in conn.execute(
                f"""
                SELECT market_id, side, COUNT(*) AS count
                FROM paper_runtime_decisions
                WHERE {current_predicate}
                GROUP BY market_id, side
                HAVING COUNT(*) > 1
                ORDER BY count DESC, market_id, side
                LIMIT 12
                """
            ).fetchall()
        ]
        diversity_row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT market_id) AS unique_markets,
                   COUNT(DISTINCT side) AS unique_sides,
                   COUNT(DISTINCT market_id || ':' || side) AS unique_market_sides,
                   COALESCE(SUM(duplicate_suppressed_count), 0) AS duplicate_suppressed,
                   COUNT(*) AS total,
                   COALESCE(MAX(group_count), 0) AS largest_group
            FROM (
                SELECT market_id, side, duplicate_suppressed_count,
                       COUNT(*) OVER (PARTITION BY market_id, side) AS group_count
                FROM paper_runtime_decisions
                WHERE {current_predicate}
            ) q
            """
        ).fetchone()
        unique_market_count = _int((diversity_row or {}).get("unique_markets"))
        unique_side_count = _int((diversity_row or {}).get("unique_sides"))
        unique_market_side_count = _int((diversity_row or {}).get("unique_market_sides"))
        duplicate_suppressed_count = _int((diversity_row or {}).get("duplicate_suppressed"))
        total_for_concentration = max(1, _int((diversity_row or {}).get("total")))
        concentration_score = round(_int((diversity_row or {}).get("largest_group")) / total_for_concentration, 4)
        if "blockers_json" in tables["paper_runtime_decisions"]:
            stale_orderbook_blocked = _count_where(conn, "paper_runtime_decisions", f"{current_predicate} AND (blockers_json ? 'STALE_ORDERBOOK' OR blockers_json ? 'MISSING_FRESH_ORDERBOOK' OR blockers_json ? 'ORDERBOOK_REFRESH_FAILED' OR blockers_json ? 'ORDERBOOK_CONNECTOR_ERROR' OR blockers_json ? 'ORDERBOOK_TTL_EXPIRED_AFTER_REFRESH')")
        if "last_mile_orderbook_refresh_attempts" in tables:
            last_mile_refresh_attempts = _count(conn, "last_mile_orderbook_refresh_attempts")
            last_mile_refresh_success = _count_where(conn, "last_mile_orderbook_refresh_attempts", "stale_cleared IS TRUE OR refresh_state IN ('REFRESHED_FRESH','FRESH_ALREADY_AVAILABLE')")
            last_mile_refresh_failed = _count_where(conn, "last_mile_orderbook_refresh_attempts", "refresh_state IN ('FAILED','BLOCKED','RATE_LIMITED_RECENT_ATTEMPT') AND COALESCE(stale_cleared,false) IS FALSE")
            stale_cleared_count = _count_where(conn, "last_mile_orderbook_refresh_attempts", "stale_cleared IS TRUE")
            stale_remaining_count = _count_where(conn, "last_mile_orderbook_refresh_attempts", "COALESCE(stale_cleared,false) IS FALSE")
    if "paper_observation_policy_reviews" in tables:
        cols = tables["paper_observation_policy_reviews"]
        if "observation_policy_state" in cols:
            paper_ready = _count_where(conn, "paper_observation_policy_reviews", "observation_policy_state='OBSERVATION_POLICY_ELIGIBLE'")
            blocked = _count_where(conn, "paper_observation_policy_reviews", "observation_policy_state='OBSERVATION_POLICY_BLOCKED'")
            watch = _count_where(conn, "paper_observation_policy_reviews", "observation_policy_state='OBSERVATION_POLICY_WATCH'")
            policy_state_counts = _group_counts_where(conn, "paper_observation_policy_reviews", "observation_policy_state", "true", limit=12)
            policy_by_market = _group_counts_where(conn, "paper_observation_policy_reviews", "market_id", "true", limit=12)
            policy_by_side = _group_counts_where(conn, "paper_observation_policy_reviews", "side", "true", limit=8)
            dominant_market_id = next(iter(policy_by_market), "")
            top_non_dominant_policy_blockers = _top_policy_blockers_by_market_side(conn, dominant_market_id=dominant_market_id, limit=12)
        if not blockers:
            blockers = _json_text_counter(conn, "paper_observation_policy_reviews", "policy_blockers_json", limit=8) if "policy_blockers_json" in cols else []
    elif "proactive_seed_mesh_results" in tables:
        cols = tables["proactive_seed_mesh_results"]
        if "opportunity_decision_band" in cols:
            paper_ready = _count_where(conn, "proactive_seed_mesh_results", "opportunity_decision_band='PAPER_OBSERVATION'")
            blocked = _count_where(conn, "proactive_seed_mesh_results", "opportunity_decision_band='HARD_BLOCKED'")
            watch = _count_where(conn, "proactive_seed_mesh_results", "opportunity_decision_band='WATCH_ONLY'")
        blockers = _json_text_counter(conn, "proactive_seed_mesh_results", "hard_blockers_json", limit=8) if "hard_blockers_json" in cols else []
    funnel_unique_pairs = _funnel_unique_pairs(conn, tables)
    if funnel_unique_pairs:
        diversity_bottleneck_stage = _diversity_bottleneck_stage(funnel_unique_pairs)
    return {
        "paper_ready_decisions": paper_ready,
        "blocked_decisions": blocked,
        "watch_decisions": watch,
        "runtime_decisions_total": runtime_total,
        "paper_enter_decisions": runtime_enter,
        "runtime_blocked_decisions": runtime_blocked,
        "runtime_watch_decisions": runtime_watch,
        "top_runtime_decisions": runtime_top,
        "top_unique_runtime_decisions": runtime_top_unique,
        "runtime_decisions_by_market": runtime_by_market,
        "runtime_decisions_by_side": runtime_by_side,
        "runtime_decisions_by_trigger_family": runtime_by_trigger_family,
        "top_duplicate_blockers_by_market_side": duplicate_by_market_side,
        "policy_state_counts": policy_state_counts,
        "policy_reviews_by_market": policy_by_market,
        "policy_reviews_by_side": policy_by_side,
        "top_non_dominant_policy_blockers": top_non_dominant_policy_blockers,
        "funnel_unique_market_side_pairs": funnel_unique_pairs,
        "diversity_bottleneck_stage": diversity_bottleneck_stage,
        "unique_market_count": unique_market_count,
        "unique_side_count": unique_side_count,
        "unique_market_side_count": unique_market_side_count,
        "duplicate_suppression_count": duplicate_suppressed_count,
        "concentration_score": concentration_score,
        "stale_orderbook_blocked_count": stale_orderbook_blocked,
        "last_mile_refresh_attempts": last_mile_refresh_attempts,
        "last_mile_refresh_success_count": last_mile_refresh_success,
        "last_mile_refresh_failed_count": last_mile_refresh_failed,
        "stale_cleared_count": stale_cleared_count,
        "stale_remaining_count": stale_remaining_count,
        "top_blockers": blockers,
    }


def _execution(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    execution = _zero_execution()
    active_session = _active_paper_session(conn, tables)
    active_session_id = str(active_session.get("paper_session_id")) if active_session else None
    for table, key in (
        ("paper_intents", "paper_intents"),
        ("paper_orders", "paper_orders"),
        ("paper_fills", "paper_fills"),
        ("paper_positions", "paper_positions"),
        ("live_orders", "live_orders"),
        ("shadow_orders", "shadow_orders"),
        ("positions", "canonical_positions"),
        ("market_link_candidates", "execution_candidates"),
    ):
        if table in tables:
            if table.startswith("paper_") and active_session_id and "paper_session_id" in tables[table]:
                execution[key] = _count_where_params(conn, table, "paper_session_id = %s", (active_session_id,))
                execution[f"historical_{key}"] = _count(conn, table)
            else:
                execution[key] = _count(conn, table)
    if "paper_positions" in tables:
        cols = tables["paper_positions"]
        if "current_status" in cols:
            predicate = "current_status IN ('OPEN','ACTIVE')"
            if "closed_at" in cols:
                predicate += " AND closed_at IS NULL"
            if "excluded_from_active_paper_truth" in cols:
                predicate += " AND excluded_from_active_paper_truth IS FALSE"
            if active_session_id and "paper_session_id" in cols:
                execution["open_paper_positions"] = _count_where_params(conn, "paper_positions", f"paper_session_id = %s AND {predicate}", (active_session_id,))
                execution["historical_open_paper_positions"] = _count_where(conn, "paper_positions", predicate)
            else:
                execution["open_paper_positions"] = _count_where(conn, "paper_positions", predicate)
        elif "status" in cols:
            execution["open_paper_positions"] = _count_where(conn, "paper_positions", "status IN ('OPEN','ACTIVE')")
        elif "closed_at" in cols:
            predicate = "closed_at IS NULL"
            if "excluded_from_active_paper_truth" in cols:
                predicate += " AND excluded_from_active_paper_truth IS FALSE"
            execution["open_paper_positions"] = _count_where(conn, "paper_positions", predicate)
    if "orders" in tables:
        execution["real_orders"] += _real_order_count(conn, "orders", tables["orders"])
    if "orders_v2" in tables:
        execution["real_orders"] += _real_order_count(conn, "orders_v2", tables["orders_v2"])
    if active_session:
        execution["paper_session_id"] = active_session_id
        execution["paper_session_starting_balance"] = _float(active_session.get("starting_balance"))
        execution["paper_session_status"] = active_session.get("status")
    return execution


def _pnl(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    active_session = _active_paper_session(conn, tables)
    active_session_id = str(active_session.get("paper_session_id")) if active_session else None
    if active_session_id:
        realized = _sum_where_params(conn, "paper_position_closes", "realized_pnl", "paper_session_id = %s", (active_session_id,)) if "paper_position_closes" in tables else 0.0
        unrealized = _sum_where_params(conn, "paper_positions", "unrealized", "paper_session_id = %s AND closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth,false)=false", (active_session_id,)) if "paper_positions" in tables else 0.0
        return {"realized": realized, "unrealized": unrealized, "daily": realized + unrealized, "status": "OK", "paper_session_id": active_session_id}
    if "paper_daily_pnl" not in tables:
        return {"realized": 0.0, "unrealized": 0.0, "daily": 0.0, "status": "MISSING"}
    cols = tables["paper_daily_pnl"]
    realized_col = _first_existing(cols, "realized_pnl", "realized")
    unrealized_col = _first_existing(cols, "unrealized_pnl", "unrealized")
    daily_col = _first_existing(cols, "net_pnl", "daily_pnl", "pnl")
    return {
        "realized": _sum(conn, "paper_daily_pnl", realized_col) if realized_col else 0.0,
        "unrealized": _sum(conn, "paper_daily_pnl", unrealized_col) if unrealized_col else 0.0,
        "daily": _sum(conn, "paper_daily_pnl", daily_col) if daily_col else 0.0,
        "status": "OK",
    }


def _paper_session_summary(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    active = _active_paper_session(conn, tables)
    if not active:
        return {"status": "NO_ACTIVE_SESSION", "active_session": None, "historical_totals": _paper_historical_totals(conn, tables)}
    session_id = str(active["paper_session_id"])
    counts = {
        "paper_intents": _count_where_params(conn, "paper_intents", "paper_session_id=%s", (session_id,)) if "paper_intents" in tables else 0,
        "paper_orders": _count_where_params(conn, "paper_orders", "paper_session_id=%s", (session_id,)) if "paper_orders" in tables else 0,
        "paper_fills": _count_where_params(conn, "paper_fills", "paper_session_id=%s", (session_id,)) if "paper_fills" in tables else 0,
        "paper_positions": _count_where_params(conn, "paper_positions", "paper_session_id=%s", (session_id,)) if "paper_positions" in tables else 0,
        "open_paper_positions": _count_where_params(conn, "paper_positions", "paper_session_id=%s AND closed_at IS NULL AND current_status IN ('OPEN','EXIT_PENDING') AND COALESCE(excluded_from_active_paper_truth,false)=false", (session_id,)) if "paper_positions" in tables else 0,
    }
    defense = _paper_defense_summary(conn, session_id)
    return {
        "status": "OK",
        "active_session": active,
        "current_session_counts": counts,
        "paper_defense": defense,
        "historical_totals": _paper_historical_totals(conn, tables),
        "previous_session": _previous_paper_session(conn, tables),
    }


def _paper_defense_summary(conn: Any, session_id: str) -> dict[str, Any]:
    try:
        from app.services.paper_defense import paper_defense_status

        return paper_defense_status(conn)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "paper_session_id": session_id, "error": f"{type(exc).__name__}: {exc}"}


def _learning(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    closed = _count(conn, "paper_position_closes") if "paper_position_closes" in tables else 0
    return {
        "closed_paper_trades": closed,
        "winning_trades": 0,
        "losing_trades": 0,
        "thesis_outcomes": _count(conn, "paper_observation_policy_reviews") if "paper_observation_policy_reviews" in tables else 0,
    }


def _zero_ai_mesh_intelligence() -> dict[str, Any]:
    return {
        "status": "MISSING",
        "ai_enabled": False,
        "ai_mode": "DISABLED",
        "local_model_status": {"available": False, "provider": "NONE"},
        "call_budget": {},
        "total_insights": 0,
        "insights_by_type": {},
        "ai_alerts": [],
        "latest_ai_error": None,
        "timeout_count": 0,
        "json_reliability_status": "UNKNOWN",
        "fast_json_model": None,
        "reasoning_model": None,
        "invalid_json_count": 0,
        "schema_invalid_count": 0,
        "repaired_json_count": 0,
        "fallback_count": 0,
        "valid_json_rate": 0.0,
        "average_latency_ms": 0,
        "p95_latency_ms": 0,
        "skipped_budget": 0,
        "skipped_cached": 0,
        "latest_successful_insight": None,
        "candidates_upgraded_by_ai": 0,
        "candidates_kept_blocked_by_ai": 0,
        "top_why_not_reasons": [],
    }


def _ai_mesh_intelligence(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "ai_mesh_insights" not in tables:
        return _zero_ai_mesh_intelligence()
    counts = {
        "total_insights": _count(conn, "ai_mesh_insights"),
        "insights_by_type": _group_counts(conn, "ai_mesh_insights", "insight_type"),
    }
    local_status: dict[str, Any] = {"available": False, "provider": "NONE"}
    latest_error = None
    latest_run = None
    if "ai_mesh_intelligence_runs" in tables:
        row = conn.execute(
            """
            SELECT *
            FROM ai_mesh_intelligence_runs
            ORDER BY completed_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ).fetchone()
        if row:
            latest_run = _json_safe(dict(row))
            local_status = latest_run.get("local_model_status_json") or local_status
            latest_error = latest_run.get("latest_error")
    alerts = [
        _json_safe(dict(row))
        for row in conn.execute(
            """
            SELECT ai_mesh_insight_id, insight_type, market_id, side, summary,
                   recommended_mesh_action, confidence, created_at
            FROM ai_mesh_insights
            WHERE insight_type='ALERT'
            ORDER BY created_at DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
    ]
    recent = [
        _json_safe(dict(row))
        for row in conn.execute(
            """
            SELECT ai_mesh_insight_id, insight_type, market_id, side, summary,
                   thesis_type, expected_hold_time_seconds, time_stop_seconds,
                   invalidation_condition, recommended_mesh_action,
                   why_not_json, missing_evidence_json, confidence, created_at
            FROM ai_mesh_insights
            ORDER BY created_at DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
    ]
    upgraded = _int(
        (
            conn.execute(
                """
                SELECT COUNT(DISTINCT proactive_candidate_seed_id) AS count
                FROM ai_mesh_insights
                WHERE proactive_candidate_seed_id IS NOT NULL
                  AND (
                    insight_type IN ('TRADE_THESIS','HOLD_TIME','EXIT_PLAN','INVALIDATION')
                    OR expected_hold_time_seconds IS NOT NULL
                    OR COALESCE(invalidation_condition,'') <> ''
                  )
                """
            ).fetchone()
            or {}
        ).get("count")
    )
    kept_blocked = _int(
        (
            conn.execute(
                """
                SELECT COUNT(DISTINCT proactive_candidate_seed_id) AS count
                FROM ai_mesh_insights
                WHERE proactive_candidate_seed_id IS NOT NULL
                  AND (why_not_json <> '[]'::jsonb OR missing_evidence_json <> '[]'::jsonb)
                """
            ).fetchone()
            or {}
        ).get("count")
    )
    metadata = latest_run.get("metadata_json") if isinstance(latest_run, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    latest_success = conn.execute(
        """
        SELECT ai_mesh_insight_id, insight_type, market_id, side, model_provider,
               model_name, summary, recommended_mesh_action, created_at
        FROM ai_mesh_insights
        WHERE model_provider <> 'NONE'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    return {
        "status": "REAL" if counts["total_insights"] else "MISSING",
        "ai_enabled": True,
        "ai_mode": metadata.get("ai_mode") or ("DEGRADED" if latest_error else "ENABLED" if local_status.get("available") else "DISABLED"),
        "local_model_status": local_status,
        "fast_json_model": local_status.get("fast_json_model") or local_status.get("fast_model"),
        "reasoning_model": local_status.get("reasoning_model"),
        "json_reliability_status": _json_reliability_status_from_metadata(latest_run, metadata),
        "call_budget": metadata.get("call_budget") or {},
        "latest_run": latest_run,
        "latest_ai_error": latest_error,
        "timeout_count": _int(metadata.get("calls_timed_out")),
        "invalid_json_count": _int(metadata.get("invalid_json_count")),
        "schema_invalid_count": _int(metadata.get("schema_invalid_count")),
        "repaired_json_count": _int(metadata.get("repaired_json_count")),
        "fallback_count": _int(metadata.get("fallback_count")),
        "valid_json_rate": float(metadata.get("valid_json_rate") or 0),
        "average_latency_ms": _int(latest_run.get("avg_latency_ms") if isinstance(latest_run, dict) else 0),
        "p95_latency_ms": _int(metadata.get("p95_latency_ms")),
        "skipped_budget": _int(metadata.get("skipped_budget")),
        "skipped_cached": _int(metadata.get("skipped_cached")),
        "skipped_low_priority": _int(metadata.get("skipped_low_priority")),
        "latest_successful_insight": _json_safe(dict(latest_success)) if latest_success else None,
        "ai_alerts": alerts,
        "recent_insights": recent,
        "candidates_upgraded_by_ai": upgraded,
        "candidates_kept_blocked_by_ai": kept_blocked,
        "top_why_not_reasons": _json_text_counter(conn, "ai_mesh_insights", "why_not_json", limit=8),
        **counts,
    }


def _runtime_truth(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any]:
    if "runtime_cycles_v2" not in tables:
        return {
            "current_active_cycle_id": None,
            "current_active_cycle_state": "MISSING",
            "latest_completed_cycle_id": None,
            "stale_abandoned_cycles_count": 0,
        }
    active = conn.execute(
        """
        SELECT cycle_id, mode, status, started_at, finished_at, metadata_json
        FROM runtime_cycles_v2
        WHERE finished_at IS NULL
          AND status IN ('RUNNING','STARTING')
          AND started_at >= now() - interval '10 minutes'
        ORDER BY started_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    latest_completed = conn.execute(
        """
        SELECT cycle_id, mode, status, started_at, finished_at, metadata_json
        FROM runtime_cycles_v2
        WHERE status IN ('COMPLETED','SAFE_STOPPED','STOPPED')
          AND finished_at IS NOT NULL
        ORDER BY finished_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    stale_abandoned = _count_where(conn, "runtime_cycles_v2", "status='STALE_ABANDONED'")
    return {
        "current_active_cycle_id": active["cycle_id"] if active else None,
        "current_active_cycle_state": active["status"] if active else "NONE",
        "current_active_cycle": _json_safe(dict(active)) if active else None,
        "latest_completed_cycle_id": latest_completed["cycle_id"] if latest_completed else None,
        "latest_completed_cycle_state": latest_completed["status"] if latest_completed else None,
        "latest_completed_cycle": _json_safe(dict(latest_completed)) if latest_completed else None,
        "stale_abandoned_cycles_count": stale_abandoned,
    }


def _stale_components(conn: Any, tables: dict[str, set[str]]) -> list[str]:
    stale: list[str] = []
    if "market_universe_memory" in tables and "freshness_state" in tables["market_universe_memory"]:
        if _count_where(conn, "market_universe_memory", "freshness_state<>'FRESH'"):
            stale.append("market_universe_memory")
    if "targeted_market_revalidations" in tables and "orderbook_refresh_state" in tables["targeted_market_revalidations"]:
        if _count_where(conn, "targeted_market_revalidations", "orderbook_refresh_state IN ('STALE','FAILED')"):
            stale.append("targeted_market_revalidation_orderbook")
    return stale


def _table_cache(conn: Any) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema()
        """
    ).fetchall()
    cache: dict[str, set[str]] = {}
    for row in rows:
        cache.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return cache


def _count(conn: Any, table: str) -> int:
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _count_where(conn: Any, table: str, predicate: str) -> int:
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}").fetchone()["count"])


def _count_where_params(conn: Any, table: str, predicate: str, params: tuple[Any, ...]) -> int:
    return _int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {predicate}", params).fetchone()["count"])


def _group_counts(conn: Any, table: str, field: str) -> dict[str, int]:
    rows = conn.execute(f"SELECT {field} AS key, COUNT(*) AS count FROM {table} GROUP BY {field}").fetchall()
    return {str(row["key"] or "UNKNOWN"): _int(row["count"]) for row in rows}


def _sum(conn: Any, table: str, field: str) -> float:
    row = conn.execute(f"SELECT COALESCE(SUM({field}), 0) AS value FROM {table}").fetchone()
    return _float(row["value"])


def _sum_where_params(conn: Any, table: str, field: str, predicate: str, params: tuple[Any, ...]) -> float:
    row = conn.execute(f"SELECT COALESCE(SUM({field}), 0) AS value FROM {table} WHERE {predicate}", params).fetchone()
    return _float(row["value"])


def _active_paper_session(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any] | None:
    if "paper_sessions" not in tables:
        return None
    row = conn.execute("SELECT * FROM paper_sessions WHERE status='ACTIVE' ORDER BY started_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _previous_paper_session(conn: Any, tables: dict[str, set[str]]) -> dict[str, Any] | None:
    if "paper_sessions" not in tables:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM paper_sessions
        WHERE status <> 'ACTIVE'
        ORDER BY closed_at DESC NULLS LAST, started_at DESC NULLS LAST, id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def _paper_historical_totals(conn: Any, tables: dict[str, set[str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes"):
        out[table] = _count(conn, table) if table in tables else 0
    return out


def _json_text_counter(conn: Any, table: str, field: str, *, limit: int, predicate: str = "true") -> list[str]:
    rows = conn.execute(
        f"""
        SELECT value, COUNT(*) AS count
        FROM {table}, jsonb_array_elements_text(COALESCE({field}, '[]'::jsonb)) AS value
        WHERE {predicate}
        GROUP BY value
        ORDER BY count DESC, value
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [f"{row['value']}: {row['count']}" for row in rows]


def _group_counts_where(conn: Any, table: str, field: str, predicate: str, *, limit: int) -> dict[str, int]:
    rows = conn.execute(
        f"""
        SELECT {field} AS key, COUNT(*) AS count
        FROM {table}
        WHERE {predicate}
        GROUP BY {field}
        ORDER BY count DESC, key
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return {str(row["key"] or "UNKNOWN"): _int(row["count"]) for row in rows}


def _top_policy_blockers_by_market_side(conn: Any, *, dominant_market_id: str, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT market_id, side, value AS blocker, COUNT(*) AS count
        FROM paper_observation_policy_reviews,
             LATERAL jsonb_array_elements_text(policy_blockers_json) AS value
        WHERE COALESCE(market_id, '') <> %s
        GROUP BY market_id, side, value
        ORDER BY count DESC, market_id, side, value
        LIMIT %s
        """,
        (dominant_market_id, limit),
    ).fetchall()
    return [
        {
            "market_id": str(row["market_id"] or "UNKNOWN"),
            "side": str(row["side"] or "UNKNOWN"),
            "blocker": str(row["blocker"]),
            "count": _int(row["count"]),
        }
        for row in rows
    ]


def _funnel_unique_pairs(conn: Any, tables: dict[str, set[str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    if "proactive_candidate_seeds" in tables and {"market_id", "side"}.issubset(tables["proactive_candidate_seeds"]):
        out["proactive_seeds"] = _int(
            (conn.execute("SELECT COUNT(DISTINCT market_id || ':' || COALESCE(side, 'SIDE_UNKNOWN')) AS count FROM proactive_candidate_seeds WHERE market_id IS NOT NULL").fetchone() or {}).get("count")
        )
    if "proactive_seed_mesh_results" in tables and "proactive_seed_mesh_inquiries" in tables:
        out["mesh_reviewed"] = _int(
            (
                conn.execute(
                    """
                    SELECT COUNT(DISTINCT COALESCE(i.market_id, s.market_id) || ':' || COALESCE(i.side, s.side, 'SIDE_UNKNOWN')) AS count
                    FROM proactive_seed_mesh_results r
                    LEFT JOIN proactive_seed_mesh_inquiries i ON i.seed_mesh_inquiry_id=r.seed_mesh_inquiry_id
                    LEFT JOIN proactive_candidate_seeds s ON s.proactive_candidate_seed_id=r.proactive_candidate_seed_id
                    WHERE COALESCE(i.market_id, s.market_id) IS NOT NULL
                    """
                ).fetchone()
                or {}
            ).get("count")
        )
    if "paper_observation_policy_reviews" in tables:
        out["policy_reviews"] = _int(
            (conn.execute("SELECT COUNT(DISTINCT market_id || ':' || COALESCE(side, 'SIDE_UNKNOWN')) AS count FROM paper_observation_policy_reviews WHERE market_id IS NOT NULL").fetchone() or {}).get("count")
        )
    if "paper_runtime_decisions" in tables:
        out["paper_runtime_decisions"] = _int(
            (conn.execute("SELECT COUNT(DISTINCT market_id || ':' || COALESCE(side, 'SIDE_UNKNOWN')) AS count FROM paper_runtime_decisions WHERE COALESCE(is_current_batch,true) IS TRUE AND market_id IS NOT NULL").fetchone() or {}).get("count")
        )
    return out


def _diversity_bottleneck_stage(unique_pairs: dict[str, int]) -> str:
    if not unique_pairs:
        return "UNKNOWN"
    ordered = [
        ("proactive_seeds", unique_pairs.get("proactive_seeds", 0)),
        ("mesh_reviewed", unique_pairs.get("mesh_reviewed", 0)),
        ("policy_reviews", unique_pairs.get("policy_reviews", 0)),
        ("paper_runtime_decisions", unique_pairs.get("paper_runtime_decisions", 0)),
    ]
    bottleneck = ordered[0][0]
    largest_drop = 0
    prior_count = ordered[0][1]
    for name, count in ordered[1:]:
        drop = max(0, prior_count - count)
        if drop > largest_drop:
            largest_drop = drop
            bottleneck = name
        prior_count = count
    return bottleneck


def _real_order_count(conn: Any, table: str, cols: set[str]) -> int:
    if "execution_mode" not in cols:
        return _count(conn, table)
    return _count_where(
        conn,
        table,
        "UPPER(execution_mode) NOT IN ('PAPER','PAPER_SIM','PAPER_SIM_EXIT','SHADOW','SHADOW_PLAN','CONTRACT_ONLY')",
    )


def _first_existing(cols: set[str], *names: str) -> str | None:
    for name in names:
        if name in cols:
            return name
    return None


def _disconnected_services(power: dict[str, Any], supervisor: dict[str, Any], source_refresh: dict[str, Any], db: dict[str, Any]) -> list[str]:
    disconnected: list[str] = []
    if str(power.get("power") or "OFF").upper() == "ON" and str(supervisor.get("supervisor_status") or "").upper() not in {"RUNNING", "DEGRADED"}:
        disconnected.append("runtime_supervisor_not_running")
    if str(power.get("power") or "OFF").upper() == "ON" and str(source_refresh.get("source_refresh_orchestrator_state") or source_refresh.get("status") or "").upper() in {"UNKNOWN", "MISSING"}:
        disconnected.append("source_refresh_state_unknown")
    if _int(db["market_universe"].get("total")) <= 14:
        disconnected.append("market_universe_small_or_unexpanded")
    return disconnected


def _next_action(*, system_power: str, execution_mode: str, markets_total: int, open_positions: int, blockers: list[Any]) -> str:
    if str(system_power).upper() != "ON":
        return "Run .\\tools\\polybot.ps1 on -mode paper for controlled PAPER adapter runtime."
    if execution_mode != "PAPER":
        return "Enable PAPER execution adapter with .\\tools\\polybot.ps1 on -mode paper."
    if markets_total <= 14:
        return "Let the universe scan complete or run the market universe refresh; current universe remains small."
    if blockers:
        return f"Review top blockers before expecting paper entries: {blockers[0]}"
    if open_positions:
        return "Monitor paper exits, PnL, and learning feedback."
    return "Continue controlled runtime cycles and verify candidates progress into paper intents naturally."


def _unique(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text and text not in out:
            out.append(text)
    return out


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _json_reliability_status_from_metadata(latest_run: dict[str, Any] | None, metadata: dict[str, Any]) -> str:
    if not latest_run:
        return "UNKNOWN"
    attempted = _int(latest_run.get("calls_attempted") if isinstance(latest_run, dict) else 0)
    valid_rate = _float(metadata.get("valid_json_rate"))
    invalid = _int(metadata.get("invalid_json_count"))
    schema_invalid = _int(metadata.get("schema_invalid_count"))
    if not attempted:
        return "NO_MODEL_CALLS"
    if valid_rate >= 0.99 and invalid == 0 and schema_invalid == 0:
        return "RELIABLE"
    if valid_rate > 0:
        return "PARTIAL"
    return "UNRELIABLE"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
