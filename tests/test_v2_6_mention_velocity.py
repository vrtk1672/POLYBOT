from __future__ import annotations

from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.service import SocialNeuronService
from app.social_neuron.mention_velocity import MentionVelocityTracker
from app.social_neuron.contracts import SocialPlatform, SocialSource, SocialSourceType
from app.social_neuron.source_registry import SocialSourceRegistry


def test_mention_velocity_burst_unique_authors_and_spam_ratio(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": "btc-market", "question": "Will BTC close above 100k?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    SocialSourceRegistry(connection_factory=factory).register_source(SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL))
    service = SocialNeuronService(connection_factory=factory)
    for idx in range(3):
        service.process_manual_social({"source_id": "manual", "platform": "manual", "text": f"BTC pumping now #BTC {idx}", "author_handle": f"user{idx}", "category": "crypto"})
    stats = MentionVelocityTracker(connection_factory=factory).compute_mentions_velocity("btc-market", 900)
    assert stats["mention_count"] >= 3
    assert stats["unique_author_count"] >= 3
    assert MentionVelocityTracker(connection_factory=factory).detect_social_burst("btc-market", 900) is True
