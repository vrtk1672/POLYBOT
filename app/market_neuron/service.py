from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.market_neuron.fee_reward_analyzer import FeeRewardAnalyzer
from app.market_neuron.liquidity_analyzer import LiquidityAnalyzer
from app.market_neuron.market_analyzer import MarketAnalyzer
from app.market_neuron.orderbook_analyzer import OrderbookAnalyzer
from app.market_neuron.technical_errors import MarketNeuronBlocked
from app.market_neuron.technical_signal_builder import TechnicalSignalBuilder
from app.market_neuron.time_analyzer import TimeAnalyzer
from app.repositories.fee_reward_signal_repository import FeeRewardSignalRepository
from app.repositories.liquidity_signal_repository import LiquiditySignalRepository
from app.repositories.market_technical_signal_repository import MarketTechnicalSignalRepository, latest_component
from app.repositories.orderbook_signal_repository import OrderbookSignalRepository
from app.repositories.time_signal_repository import TimeSignalRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class MarketNeuronService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        state_governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.market_analyzer = MarketAnalyzer()
        self.orderbook_analyzer = OrderbookAnalyzer()
        self.liquidity_analyzer = LiquidityAnalyzer()
        self.time_analyzer = TimeAnalyzer()
        self.fee_reward_analyzer = FeeRewardAnalyzer()
        self.builder = TechnicalSignalBuilder()
        self.market_repo = MarketTechnicalSignalRepository()
        self.orderbook_repo = OrderbookSignalRepository()
        self.liquidity_repo = LiquiditySignalRepository()
        self.time_repo = TimeSignalRepository()
        self.fee_repo = FeeRewardSignalRepository()

    def analyze_market(
        self,
        market_id: str,
        *,
        token_id: str | None = None,
        side: str = "UNKNOWN",
        raw_market_snapshot: dict[str, Any] | None = None,
        raw_orderbook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._assert_analysis_allowed()
        if not self._factory.enabled:
            snapshots = [raw_market_snapshot] if raw_market_snapshot else []
            market = self.market_analyzer.analyze(market_id, snapshots)
            orderbook = self.orderbook_analyzer.analyze(market_id, token_id=token_id, side=side, raw_orderbook=raw_orderbook)
            liquidity = self.liquidity_analyzer.analyze(orderbook)
            time_signal = self.time_analyzer.analyze(market_id, snapshot=raw_market_snapshot)
            fee_reward = self.fee_reward_analyzer.analyze(orderbook, liquidity)
            truth = self.builder.build_truth(market, orderbook, liquidity, time_signal, fee_reward)
            return truth.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            snapshot_rows = conn.execute(
                "SELECT * FROM market_snapshots_v2 WHERE market_id = %s ORDER BY snapshot_at DESC, id DESC LIMIT 40",
                (market_id,),
            ).fetchall()
            snapshots = list(reversed(snapshot_rows))
            if raw_market_snapshot:
                raw_market_snapshot = {**raw_market_snapshot, "snapshot_at": raw_market_snapshot.get("snapshot_at") or datetime.now(UTC)}
                snapshots.append(raw_market_snapshot)
            latest_snapshot = snapshots[-1] if snapshots else {}
            orderbook_snapshot = None
            if raw_orderbook is None:
                if token_id is None:
                    orderbook_snapshot = conn.execute(
                        """
                        SELECT * FROM orderbook_snapshots
                        WHERE market_id = %s
                        ORDER BY snapshot_at DESC, id DESC
                        LIMIT 1
                        """,
                        (market_id,),
                    ).fetchone()
                else:
                    orderbook_snapshot = conn.execute(
                        """
                        SELECT * FROM orderbook_snapshots
                        WHERE market_id = %s
                          AND token_id = %s
                        ORDER BY snapshot_at DESC, id DESC
                        LIMIT 1
                        """,
                        (market_id, token_id),
                    ).fetchone()
            fee_snapshot = conn.execute(
                """
                SELECT * FROM fee_snapshots
                WHERE market_id = %s
                ORDER BY snapshot_at DESC, id DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
            market = self.market_analyzer.analyze(market_id, snapshots)
            orderbook = self.orderbook_analyzer.analyze(market_id, token_id=token_id, side=side, snapshot=orderbook_snapshot, raw_orderbook=raw_orderbook)
            liquidity = self.liquidity_analyzer.analyze(orderbook)
            time_signal = self.time_analyzer.analyze(market_id, snapshot=latest_snapshot)
            fee_reward = self.fee_reward_analyzer.analyze(orderbook, liquidity, fee_snapshot=fee_snapshot)
            truth = self.builder.build_truth(market, orderbook, liquidity, time_signal, fee_reward)
            self.orderbook_repo.insert_signal(conn, orderbook)
            self.liquidity_repo.insert_signal(conn, liquidity)
            self.time_repo.insert_signal(conn, time_signal)
            self.fee_repo.insert_signal(conn, fee_reward)
            row = self.market_repo.insert_truth(conn, truth)
            self._publish_events(truth)
            result = truth.model_dump(mode="json")
            result["row_id"] = row.get("id") if isinstance(row, dict) else None
            return result

    def latest_market_truth(self, market_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"market_id": market_id, "market_signal": None, "orderbook_signal": None, "liquidity_signal": None, "time_signal": None, "fee_reward_signal": None}
        with self._factory.connect() as conn:
            return {
                "market_id": market_id,
                "market_signal": _serialize(self.market_repo.latest_for_market(conn, market_id)),
                "orderbook_signal": _serialize(latest_component(conn, "orderbook_signals", market_id)),
                "liquidity_signal": _serialize(latest_component(conn, "liquidity_signals", market_id)),
                "time_signal": _serialize(latest_component(conn, "time_signals", market_id)),
                "fee_reward_signal": _serialize(latest_component(conn, "fee_reward_signals", market_id)),
            }

    def recent_signals(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.market_repo.list_recent(conn, limit=limit)]

    def recent_blocked(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.market_repo.list_blocked(conn, limit=limit)]

    def top_markets(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.market_repo.list_top(conn, limit=limit)]

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DISABLED", "last_signal_ts": None, "signals_today": 0, "errors_today": 0, "stale_count": 0}
        try:
            with self._factory.connect() as conn:
                row = self.market_repo.health(conn)
            return {
                "status": "HEALTHY" if row and row.get("last_signal_ts") else "EMPTY",
                "last_signal_ts": _iso(row.get("last_signal_ts")) if row else None,
                "signals_today": int((row or {}).get("signals_today") or 0),
                "errors_today": 0,
                "stale_count": int((row or {}).get("stale_count") or 0),
            }
        except Exception as exc:
            return {"status": "ERROR", "last_signal_ts": None, "signals_today": 0, "errors_today": 1, "stale_count": 0, "error": str(exc)}

    def _assert_analysis_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.COLLECT_DATA)
        except Exception as exc:
            raise MarketNeuronBlocked("market technical analysis blocked by runtime mode") from exc

    def _publish_events(self, truth) -> None:
        payload = {"market_id": truth.market_id, "technical_score": truth.technical_score, "technical_blocked": truth.technical_blocked, "block_reasons": truth.block_reasons}
        self._event_bus.publish(EventType.MARKET_TECHNICAL_SIGNAL_CREATED.value, payload, "market_neuron", aggregate_type="market", aggregate_id=truth.market_id)
        self._event_bus.publish(EventType.ORDERBOOK_SIGNAL_CREATED.value, {"market_id": truth.market_id, "has_bid_ask": truth.orderbook_signal.has_bid_ask, "block_reason": truth.orderbook_signal.block_reason}, "market_neuron", aggregate_type="market", aggregate_id=truth.market_id)
        self._event_bus.publish(EventType.LIQUIDITY_SIGNAL_CREATED.value, {"market_id": truth.market_id, "exit_quality_score": truth.liquidity_signal.exit_quality_score, "block_reason": truth.liquidity_signal.block_reason}, "market_neuron", aggregate_type="market", aggregate_id=truth.market_id)
        self._event_bus.publish(EventType.TIME_SIGNAL_CREATED.value, {"market_id": truth.market_id, "ttl_bucket": truth.time_signal.ttl_bucket, "urgency_score": truth.time_signal.urgency_score}, "market_neuron", aggregate_type="market", aggregate_id=truth.market_id)
        self._event_bus.publish(EventType.FEE_REWARD_SIGNAL_CREATED.value, {"market_id": truth.market_id, "friction_score": truth.fee_reward_signal.friction_score}, "market_neuron", aggregate_type="market", aggregate_id=truth.market_id)
        self._event_bus.publish(EventType.MARKET_TECHNICAL_TRUTH_CREATED.value, payload, "market_neuron", aggregate_type="market", aggregate_id=truth.market_id)
        if truth.technical_blocked:
            self._event_bus.publish(EventType.MARKET_TECHNICAL_TRUTH_BLOCKED.value, payload, "market_neuron", aggregate_type="market", aggregate_id=truth.market_id)


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _iso(value) for key, value in dict(row).items()}
