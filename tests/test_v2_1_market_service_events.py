from __future__ import annotations

import pytest

from app.config import Settings
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.events.types import EventType
from app.ingestion.market_service import MarketService
from app.runtime.state_governor import StateGovernor


class FakeGammaClient:
    async def fetch_active_events(self):
        return [
            {
                "id": "event-1",
                "title": "Will V2.1 publish events?",
                "slug": "v21-events",
                "markets": [
                    {
                        "id": "market-1",
                        "question": "Will V2.1 publish events?",
                        "slug": "v21-events-market",
                        "outcomes": ["Yes", "No"],
                        "outcomePrices": ["0.42", "0.58"],
                        "volume": "1000",
                        "volume24hr": "100",
                        "liquidity": "500",
                        "active": True,
                        "closed": False,
                        "acceptingOrders": True,
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
    return Settings(
        refresh_interval_seconds=60,
        gamma_max_pages=1,
        gamma_page_limit=10,
        top_n=3,
    )


@pytest.mark.asyncio
async def test_market_service_publishes_cycle_and_snapshot_events(postgres_test_schema) -> None:
    run_migrations()
    StateGovernor().ensure_initial_state()
    service = MarketService(
        settings=_settings(),
        gamma_client=FakeGammaClient(),
        runtime_intelligence=NoopRuntimeIntelligence(),
    )
    await service.refresh()
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute("SELECT event_type FROM event_log ORDER BY id").fetchall()
    event_types = [row["event_type"] for row in rows]
    assert EventType.RUNTIME_CYCLE_STARTED.value in event_types
    assert EventType.MARKET_SNAPSHOT_CREATED.value in event_types
    assert EventType.RUNTIME_CYCLE_FINISHED.value in event_types


@pytest.mark.asyncio
async def test_event_publishing_does_not_break_refresh(postgres_test_schema) -> None:
    run_migrations()
    StateGovernor().ensure_initial_state()
    service = MarketService(
        settings=_settings(),
        gamma_client=FakeGammaClient(),
        runtime_intelligence=NoopRuntimeIntelligence(),
    )
    await service.refresh()
    health = await service.health()
    assert health["last_error"] is None


@pytest.mark.asyncio
async def test_kill_does_not_trigger_trading_side_effect_events(postgres_test_schema) -> None:
    run_migrations()
    governor = StateGovernor()
    governor.ensure_initial_state()
    governor.activate_kill(actor="operator", reason="event guard")
    service = MarketService(
        settings=_settings(),
        gamma_client=FakeGammaClient(),
        runtime_intelligence=NoopRuntimeIntelligence(),
    )
    await service.refresh()
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute(
            "SELECT event_type FROM event_log WHERE event_type IN ('order.created', 'order.intent.created')"
        ).fetchall()
    assert rows == []
