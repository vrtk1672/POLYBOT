from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.ingestion.market_service import MarketService


class FakeGammaClient:
    def __init__(self, events: list[dict]):
        self._events = events

    async def fetch_active_events(self) -> list[dict]:
        return self._events

    async def aclose(self) -> None:
        return None


def sample_event() -> dict:
    now = datetime.now(UTC)
    return {
        "id": "event-1",
        "title": "Sample Event",
        "commentCount": 33,
        "volume24hr": 40_000,
        "markets": [
            {
                "id": "market-1",
                "question": "High quality market?",
                "slug": "high-quality-market",
                "endDate": (now + timedelta(days=5)).isoformat(),
                "outcomePrices": "[\"0.44\", \"0.56\"]",
                "lastTradePrice": 0.44,
                "bestBid": 0.43,
                "bestAsk": 0.45,
                "liquidityClob": 150_000,
                "volumeClob": 800_000,
                "volume24hrClob": 90_000,
                "active": True,
                "closed": False,
                "acceptingOrders": True,
                "updatedAt": (now - timedelta(minutes=10)).isoformat(),
            },
            {
                "id": "market-2",
                "question": "Closed market should be ignored",
                "slug": "closed-market",
                "active": True,
                "closed": True,
                "acceptingOrders": False,
            },
            {
                "id": "market-3",
                "question": "Secondary market",
                "slug": "secondary-market",
                "endDate": (now + timedelta(days=40)).isoformat(),
                "outcomePrices": "[\"0.15\", \"0.85\"]",
                "lastTradePrice": 0.15,
                "liquidity": "12000",
                "volume": "45000",
                "volume24hr": 1500,
                "active": True,
                "closed": False,
                "acceptingOrders": True,
                "updatedAt": (now - timedelta(hours=12)).isoformat(),
            },
        ],
    }


@pytest.mark.asyncio
async def test_market_service_normalizes_and_ranks_top_n() -> None:
    settings = Settings(top_n=1)
    service = MarketService(settings=settings, gamma_client=FakeGammaClient([sample_event()]))

    await service.refresh()

    counts = await service.raw_counts()
    top_items = await service.top_markets()

    assert counts["raw_event_count"] == 1
    assert counts["normalized_market_count"] == 2
    assert len(top_items) == 1
    assert top_items[0].market.market_id == "market-1"
    assert top_items[0].market.question == "High quality market?"


@pytest.mark.asyncio
async def test_market_service_reports_fetch_error_without_crashing() -> None:
    class BrokenGammaClient(FakeGammaClient):
        async def fetch_active_events(self) -> list[dict]:
            raise RuntimeError("Gamma unavailable")

    service = MarketService(settings=Settings(), gamma_client=BrokenGammaClient([]))

    await service.refresh()
    health = await service.health()

    assert health["status"] == "degraded"
    assert health["last_error"] == "Gamma unavailable"
