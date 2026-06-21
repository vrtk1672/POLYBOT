from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.ingestion.market_service import MarketService
from app.runtime.state_governor import StateGovernor


class FakeGammaClient:
    async def fetch_active_events(self):
        return [
            {
                "id": "e1",
                "title": "Event",
                "markets": [
                    {
                        "id": "m1",
                        "question": "Will V2.2 store data?",
                        "slug": "v22-data",
                        "active": True,
                        "closed": False,
                        "acceptingOrders": True,
                        "outcomePrices": ["0.5", "0.5"],
                        "bestBid": "0.49",
                        "bestAsk": "0.51",
                        "volume24hr": "100",
                        "liquidity": "1000",
                        "clobTokenIds": ["yes", "no"],
                        "description": "Resolve based on official result",
                        "endDate": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    }
                ],
            }
        ]

    async def aclose(self):
        return None


class NoopRuntimeIntelligence:
    def refresh(self, *, cycle_id, scored_markets):
        return None


def _settings() -> Settings:
    return Settings(refresh_interval_seconds=60, gamma_max_pages=1, gamma_page_limit=10, top_n=3)


@pytest.mark.asyncio
async def test_market_service_path_upserts_v2_data(postgres_test_schema) -> None:
    run_migrations()
    StateGovernor().ensure_initial_state()
    service = MarketService(settings=_settings(), gamma_client=FakeGammaClient(), runtime_intelligence=NoopRuntimeIntelligence())
    await service.refresh()
    with DatabaseConnectionFactory().connect() as conn:
        market = conn.execute("SELECT * FROM markets_v2 WHERE market_id='m1'").fetchone()
        snapshot = conn.execute("SELECT * FROM market_snapshots_v2 WHERE market_id='m1'").fetchone()
        event = conn.execute("SELECT * FROM event_log WHERE event_type='market.snapshot.created'").fetchone()
        orderbook_count = conn.execute("SELECT COUNT(*) AS count FROM orderbook_snapshots").fetchone()["count"]
    assert market is not None
    assert snapshot is not None
    assert event is not None
    assert orderbook_count == 0
