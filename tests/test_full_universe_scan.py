from __future__ import annotations

import asyncio
import json

from app.config import Settings
from app.ingestion.market_service import MarketService


class _Gamma:
    def __init__(self, markets: list[dict]) -> None:
        self._markets = markets

    async def fetch_active_events(self):
        return [{"id": "event-1", "title": "Universe Event", "markets": self._markets}]

    async def aclose(self) -> None:
        return None


class _Foundation:
    def __init__(self) -> None:
        self.markets_seen = 0
        self.limit = None

    def process_markets(self, markets, *, cycle_id=None, correlation_id=None, limit=None):
        self.markets_seen = len(markets)
        self.limit = limit
        return {"markets_seen": len(markets[: limit or len(markets)]), "markets_created": 0, "snapshots_created": 0, "rules_updated": 0}


def _market(index: int) -> dict:
    return {
        "id": f"m-{index}",
        "question": f"Will market {index} resolve yes?",
        "slug": f"market-{index}",
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "outcomePrices": json.dumps(["0.51", "0.49"]),
        "bestBid": "0.50",
        "bestAsk": "0.52",
        "spread": "0.02",
        "liquidityNum": "1000",
        "volumeNum": "2000",
        "volume24hr": "50",
    }


def test_market_service_persists_universe_limit_not_dashboard_top_n() -> None:
    settings = Settings(top_n=2, market_universe_persist_limit=5)
    service = MarketService(settings=settings, gamma_client=_Gamma([_market(i) for i in range(5)]))
    foundation = _Foundation()
    service._data_foundation = foundation

    asyncio.run(service.refresh())

    assert foundation.markets_seen == 5
    assert foundation.limit == 5


def test_market_universe_persist_limit_can_exceed_top_n() -> None:
    settings = Settings(top_n=10, market_universe_persist_limit=1000)
    assert settings.market_universe_persist_limit > settings.top_n
