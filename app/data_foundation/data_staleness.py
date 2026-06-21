from __future__ import annotations

from datetime import UTC, datetime, timedelta


class DataStalenessPolicy:
    def __init__(
        self,
        *,
        market_snapshot_seconds: int = 300,
        orderbook_seconds: int = 60,
        rules_seconds: int = 86400,
    ) -> None:
        self.market_snapshot_seconds = market_snapshot_seconds
        self.orderbook_seconds = orderbook_seconds
        self.rules_seconds = rules_seconds

    def is_market_snapshot_stale(self, snapshot_at: datetime | None) -> bool:
        return self._is_stale(snapshot_at, self.market_snapshot_seconds)

    def is_orderbook_stale(self, snapshot_at: datetime | None) -> bool:
        return self._is_stale(snapshot_at, self.orderbook_seconds)

    def is_rules_stale(self, last_seen_at: datetime | None) -> bool:
        return self._is_stale(last_seen_at, self.rules_seconds)

    def stale_reasons(
        self,
        *,
        market_snapshot_at: datetime | None = None,
        orderbook_snapshot_at: datetime | None = None,
        rules_seen_at: datetime | None = None,
    ) -> list[str]:
        reasons: list[str] = []
        if self.is_market_snapshot_stale(market_snapshot_at):
            reasons.append("market_snapshot_stale")
        if self.is_orderbook_stale(orderbook_snapshot_at):
            reasons.append("orderbook_stale")
        if self.is_rules_stale(rules_seen_at):
            reasons.append("rules_stale")
        return reasons

    @staticmethod
    def _is_stale(value: datetime | None, threshold_seconds: int) -> bool:
        if value is None:
            return True
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return datetime.now(UTC) - value > timedelta(seconds=threshold_seconds)
