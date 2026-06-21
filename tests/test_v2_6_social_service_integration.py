from __future__ import annotations

from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.contracts import SocialPlatform, SocialSource, SocialSourceType
from app.social_neuron.service import SocialNeuronService
from app.social_neuron.source_registry import SocialSourceRegistry


def test_manual_social_goes_through_full_pipeline(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    SocialSourceRegistry(connection_factory=factory).register_source(SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL, category="crypto"))
    MarketRegistry().upsert_market(MarketRegistry().normalize_market({"id": "btc-market", "question": "Will BTC close above 100k?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    summary = SocialNeuronService(connection_factory=factory).process_manual_social({"source_id": "manual", "platform": "manual", "text": "BTC is moving fast, traders watching #BTC", "author_handle": "tester", "category": "crypto"})
    assert summary["normalized_event_id"]
    assert summary["dedup_group_id"]
    assert summary["noise_score"] >= 0
    assert summary["link_count"] >= 1
    assert summary["sentiment_count"] >= 1
    assert summary["hype_count"] >= 1
    assert summary["narrative_id"]
