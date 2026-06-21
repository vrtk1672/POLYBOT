from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.data_foundation.contracts import FeeSnapshot
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.fee_snapshot_repository import FeeSnapshotRepository


class FeesRewardsCollector:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = FeeSnapshotRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def extract_fees_rewards(
        self,
        raw_market: dict[str, Any],
        *,
        market_id: str,
        spread: float | None = None,
        estimated_slippage_cost: float | None = None,
    ) -> FeeSnapshot:
        maker_fee = _float(raw_market.get("makerFee") or raw_market.get("maker_fee"))
        taker_fee = _float(raw_market.get("takerFee") or raw_market.get("taker_fee"))
        reward_pool = _float(raw_market.get("rewards") or raw_market.get("rewardPool") or raw_market.get("reward_pool"))
        reward_rate = _float(raw_market.get("rewardRate") or raw_market.get("reward_rate"))
        spread_cost = round(float(spread) / 2, 6) if spread is not None else None
        costs = [value for value in (maker_fee, taker_fee, spread_cost, estimated_slippage_cost) if value is not None]
        reward = reward_rate or 0
        net_edge_adjustment = round(reward - sum(costs), 6) if costs or reward_rate is not None else None
        return FeeSnapshot(
            fee_snapshot_id=f"fee_{uuid4().hex}",
            market_id=market_id,
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            spread_cost=spread_cost,
            estimated_slippage_cost=estimated_slippage_cost,
            reward_pool=reward_pool,
            reward_rate=reward_rate,
            net_edge_adjustment=net_edge_adjustment,
            raw_fee_json={
                key: raw_market.get(key)
                for key in ("makerFee", "takerFee", "rewards", "rewardPool", "rewardRate")
                if key in raw_market
            },
            metadata_json={"fees_available": maker_fee is not None or taker_fee is not None, "rewards_available": reward_pool is not None or reward_rate is not None},
        )

    def persist_fee_snapshot(self, snapshot: FeeSnapshot) -> None:
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.append_snapshot(conn, snapshot)
        self._publish(snapshot)

    def _publish(self, snapshot: FeeSnapshot) -> None:
        try:
            self._event_bus.publish(
                EventType.FEE_SNAPSHOT_CREATED.value,
                {"market_id": snapshot.market_id, "fee_snapshot_id": snapshot.fee_snapshot_id, "net_edge_adjustment": snapshot.net_edge_adjustment},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=snapshot.market_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            return


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
