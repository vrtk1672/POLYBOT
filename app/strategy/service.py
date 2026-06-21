from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.engine_cooldown_repository import EngineCooldownRepository
from app.repositories.engine_decision_repository import EngineDecisionRepository
from app.repositories.engine_rejection_repository import EngineRejectionRepository
from app.repositories.strategy_route_repository import StrategyRouteRepository
from app.repositories.strategy_route_run_repository import StrategyRouteRunRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.strategy.contracts import StrategyRouteInput, StrategyRunResult, bounded
from app.strategy.engine_cooldown_manager import EngineCooldownManager
from app.strategy.router import StrategyRouter
from app.strategy.strategy_errors import StrategyRoutingBlocked


class StrategyService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, state_governor: StateGovernor | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.router = StrategyRouter()
        self.run_repo = StrategyRouteRunRepository()
        self.route_repo = StrategyRouteRepository()
        self.decision_repo = EngineDecisionRepository()
        self.rejection_repo = EngineRejectionRepository()
        self.cooldown_repo = EngineCooldownRepository()
        self.cooldowns = EngineCooldownManager()

    def route_market(self, market_id: str, *, side: str | None = None, dry_run: bool = False, manual_input: dict[str, Any] | None = None, hunt_approval: bool = False) -> dict[str, Any]:
        self._assert_allowed()
        if not self._factory.enabled:
            return {"dry_run": dry_run, "written": False, "error": "database_disabled"}
        run_id = f"strategy_{uuid4().hex}"
        with self._factory.connect() as conn:
            payload = self._build_input(conn, market_id, side=side, manual=manual_input, hunt_approval=hunt_approval)
            route = self.router.route(payload)
            result = StrategyRunResult(run_id=run_id, market_id=market_id, side=route.side, route=route, persisted=False)
            if dry_run:
                return {"dry_run": True, "written": False, "result": result.model_dump(mode="json")}
            with conn.transaction():
                self.run_repo.insert_started(
                    conn,
                    run_id=run_id,
                    market_id=market_id,
                    market_family=payload.market_family,
                    side=route.side,
                    opportunity_run_id=payload.opportunity_run_id,
                    opportunity_score_id=payload.opportunity_score_id,
                    runtime_mode=self._runtime_mode(),
                    input_sources=_input_sources(payload),
                    input_completeness_score=payload.data_completeness_score,
                )
                self.route_repo.insert(conn, run_id, payload.market_family, route)
                self.decision_repo.insert_many(conn, run_id, market_id, route.engine_decisions)
                self.rejection_repo.insert_many(conn, run_id, market_id, route.engine_rejections)
                cooldown_created = None
                if route.cooldown_required:
                    cooldown = self.cooldowns.cooldown_for_rejections([rej.model_dump() | {"market_id": market_id} for rej in route.engine_rejections])
                    if cooldown:
                        cooldown_created = self.cooldown_repo.insert(conn, source_run_id=run_id, **cooldown)
                self.run_repo.finish(conn, run_id)
            conn.commit()
        self._publish(run_id, route, cooldown_created=cooldown_created)
        result.persisted = True
        return {"dry_run": False, "written": True, "result": result.model_dump(mode="json")}

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty("DISABLED")
        try:
            with self._factory.connect() as conn:
                exists = conn.execute("SELECT to_regclass('strategy_routes_v2') AS name").fetchone()
                if exists is None or exists["name"] is None:
                    return _empty("EMPTY")
                run_health = self.run_repo.health(conn)
                stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS routes_today,
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND route_status = 'NO_TRADE') AS no_trade_today,
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND route_status = 'BLOCKED') AS blocked_today,
                      MAX(created_at) AS latest_route_ts
                    FROM strategy_routes_v2
                    """
                ).fetchone()
                cooldowns = conn.execute("SELECT COUNT(*) AS count FROM engine_cooldowns WHERE active IS TRUE AND (expires_at IS NULL OR expires_at > now())").fetchone()
            return {
                "status": "HEALTHY" if (stats or {}).get("latest_route_ts") else "EMPTY",
                "runs_today": int((run_health or {}).get("runs_today") or 0),
                "routes_today": int((stats or {}).get("routes_today") or 0),
                "no_trade_today": int((stats or {}).get("no_trade_today") or 0),
                "blocked_today": int((stats or {}).get("blocked_today") or 0),
                "cooldowns_active": int((cooldowns or {}).get("count") or 0),
                "latest_route_ts": _iso((stats or {}).get("latest_route_ts")),
                "errors_today": int((run_health or {}).get("errors_today") or 0),
            }
        except Exception as exc:
            data = _empty("ERROR")
            data["errors_today"] = 1
            data["error"] = str(exc)
            return data

    def latest_for_market(self, market_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return _serialize(self.route_repo.latest_for_market(conn, market_id)) or {"market_id": market_id, "route": None}

    def recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.route_repo.recent(conn, limit=limit)]

    def engines(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.decision_repo.summary(conn)]

    def rejections_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.rejection_repo.recent(conn, limit=limit)]

    def cooldowns_active(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.cooldown_repo.active(conn)]

    def run_detail(self, run_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return {
                "run_id": run_id,
                "route": _serialize(self.route_repo.by_run(conn, run_id)),
                "engine_decisions": [_serialize(row) for row in self.decision_repo.by_run(conn, run_id)],
                "engine_rejections": [_serialize(row) for row in self.rejection_repo.by_run(conn, run_id)],
            }

    def _build_input(self, conn: Connection, market_id: str, *, side: str | None, manual: dict[str, Any] | None, hunt_approval: bool) -> StrategyRouteInput:
        manual = manual or {}
        if manual:
            return StrategyRouteInput(market_id=market_id, side=side or manual.get("side") or "UNKNOWN", hunt_approval=hunt_approval or bool(manual.get("hunt_approval")), **{k: v for k, v in manual.items() if k not in {"market_id", "side", "hunt_approval"}})
        score = _latest(conn, "opportunity_scores_v2", market_id)
        risk_flags = _rows(conn, "opportunity_risk_flags", market_id, "created_at", 20)
        if not score:
            return StrategyRouteInput(market_id=market_id, side=side or "UNKNOWN", insufficient_data_reasons=["missing_opportunity_score"], hunt_approval=hunt_approval)
        components = {
            key: score.get(key)
            for key in (
                "edge", "confidence", "trigger_strength", "repricing_potential", "time_efficiency",
                "liquidity_quality", "exit_probability", "capital_recycling_speed", "convexity",
                "balance_fit", "fee_reward_advantage", "risk_penalty", "slippage_penalty",
                "lockup_penalty", "correlation_risk", "trap_risk", "wording_risk",
                "adverse_selection_risk", "already_priced_in_score",
            )
        }
        components["capital_allowed"] = score.get("capital_allowed")
        context = _latest(conn, "context_brain_outputs", market_id) or {}
        capital = _latest(conn, "capital_brain_outputs", market_id) or {}
        technical = {
            "market_signal": _latest(conn, "market_technical_signals", market_id, order_by="ts") or {},
            "orderbook_signal": _latest(conn, "orderbook_signals", market_id, order_by="ts") or {},
            "liquidity_signal": _latest(conn, "liquidity_signals", market_id, order_by="ts") or {},
        }
        memory = _latest(conn, "market_memory_v2", market_id, order_by="updated_at") or {}
        return StrategyRouteInput(
            market_id=market_id,
            market_family=score.get("market_family"),
            side=side or score.get("side") or "UNKNOWN",
            opportunity_run_id=score.get("run_id"),
            opportunity_score_id=score.get("id"),
            opportunity_score=score.get("opportunity_score") or 0,
            opportunity_score_band=score.get("score_band") or "LOW",
            opportunity_components=components,
            opportunity_risk_flags=risk_flags,
            opportunity_no_trade_reasons=score.get("no_trade_reasons_json") or [],
            candidate_engines_from_opportunity=score.get("candidate_engines_json") or [],
            context_output=context,
            capital_output=capital,
            technical_truth=technical,
            market_memory=memory,
            data_completeness_score=bounded(score.get("confidence")),
            insufficient_data_reasons=score.get("insufficient_data_reasons_json") or [],
            hunt_approval=hunt_approval,
        )

    def _assert_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.SCORE_MARKET)
        except Exception as exc:
            raise StrategyRoutingBlocked("strategy routing blocked by runtime mode") from exc

    def _runtime_mode(self) -> str | None:
        try:
            return self._governor.get_current_state().current_mode.value
        except Exception:
            return None

    def _publish(self, run_id: str, route, *, cooldown_created: dict[str, Any] | None = None) -> None:
        payload = {
            "run_id": run_id,
            "market_id": route.market_id,
            "selected_engine": route.selected_engine,
            "route_status": route.route_status,
            "route_confidence": route.route_confidence,
            "insufficient_data": route.insufficient_data,
        }
        self._event_bus.publish(EventType.STRATEGY_ROUTE_RUN_STARTED.value, {"run_id": run_id, "market_id": route.market_id}, "strategy", aggregate_type="market", aggregate_id=route.market_id)
        self._event_bus.publish(EventType.STRATEGY_ROUTE_CREATED.value, payload, "strategy", aggregate_type="market", aggregate_id=route.market_id)
        for decision in route.engine_decisions:
            self._event_bus.publish(EventType.STRATEGY_ENGINE_DECISION_CREATED.value, {"run_id": run_id, "market_id": route.market_id, "engine": decision.engine, "eligible": decision.eligible, "selected": decision.selected}, "strategy", aggregate_type="market", aggregate_id=route.market_id)
        for rejection in route.engine_rejections:
            self._event_bus.publish(EventType.STRATEGY_ENGINE_REJECTED.value, {"run_id": run_id, "market_id": route.market_id, "engine": rejection.engine, "reason": rejection.rejection_reason}, "strategy", aggregate_type="market", aggregate_id=route.market_id)
        if route.selected_engine == "NO_TRADE":
            self._event_bus.publish(EventType.STRATEGY_ROUTE_NO_TRADE.value, payload, "strategy", aggregate_type="market", aggregate_id=route.market_id)
        if route.insufficient_data:
            self._event_bus.publish(EventType.STRATEGY_ROUTE_INSUFFICIENT_DATA.value, payload, "strategy", aggregate_type="market", aggregate_id=route.market_id)
        if cooldown_created:
            self._event_bus.publish(EventType.STRATEGY_ENGINE_COOLDOWN_CREATED.value, {"run_id": run_id, "market_id": route.market_id, "engine": cooldown_created.get("engine"), "reason": cooldown_created.get("reason")}, "strategy", aggregate_type="market", aggregate_id=route.market_id)


def _exists(conn: Connection, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is not None


def _latest(conn: Connection, table: str, market_id: str, *, order_by: str = "created_at") -> dict[str, Any] | None:
    if not _exists(conn, table):
        return None
    rows = conn.execute(f"SELECT * FROM {table} WHERE market_id = %s ORDER BY {order_by} DESC, id DESC LIMIT 1", (market_id,)).fetchall()
    return dict(rows[0]) if rows else None


def _rows(conn: Connection, table: str, market_id: str, order_by: str, limit: int) -> list[dict[str, Any]]:
    if not _exists(conn, table):
        return []
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE market_id = %s ORDER BY {order_by} DESC, id DESC LIMIT %s", (market_id, limit)).fetchall()]


def _input_sources(payload: StrategyRouteInput) -> list[str]:
    sources = ["opportunity_score"] if payload.opportunity_run_id else []
    if payload.context_output:
        sources.append("context_brain")
    if payload.capital_output:
        sources.append("capital_brain")
    if payload.technical_truth:
        sources.append("market_technical")
    if payload.market_memory:
        sources.append("market_memory")
    return sources


def _empty(status: str) -> dict[str, Any]:
    return {"status": status, "runs_today": 0, "routes_today": 0, "no_trade_today": 0, "blocked_today": 0, "cooldowns_active": 0, "latest_route_ts": None, "errors_today": 0}


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _iso(value) for key, value in dict(row).items()}
