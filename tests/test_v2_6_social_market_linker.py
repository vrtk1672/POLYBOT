from __future__ import annotations

from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.contracts import NormalizedSocialEvent, SocialDirection
from app.social_neuron.market_linker import SocialMarketLinker


def test_social_linked_only_when_justified_and_closed_penalized(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": "btc-market", "question": "Will BTC close above 100k?", "category": "crypto", "active": True, "closed": False, "clobTokenIds": ["yes", "no"]}))
    registry.upsert_market(registry.normalize_market({"id": "closed-btc", "question": "Will BTC close above 100k?", "category": "crypto", "active": False, "closed": True, "clobTokenIds": ["yes", "no"]}))
    linker = SocialMarketLinker(connection_factory=DatabaseConnectionFactory())
    event = NormalizedSocialEvent(source_id="manual", text="BTC traders say yes", normalized_text="btc traders say yes", category="crypto", entities=["BTC"])
    links = linker.link_social_to_markets(event)
    assert any(link.market_id == "btc-market" for link in links)
    assert all(link.sentiment_direction in {SocialDirection.YES, SocialDirection.UNKNOWN} for link in links)
    irrelevant = NormalizedSocialEvent(source_id="manual", text="cooking dinner", normalized_text="cooking dinner")
    assert linker.link_social_to_markets(irrelevant) == []
