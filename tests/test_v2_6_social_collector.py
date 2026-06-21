from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.collector import SocialCollector
from app.social_neuron.contracts import SocialPlatform, SocialSource, SocialSourceType
from app.social_neuron.source_registry import SocialSourceRegistry


def test_manual_item_collected_deduped_and_bad_source_status(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    SocialSourceRegistry(connection_factory=factory).register_source(SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL))
    collector = SocialCollector(connection_factory=factory)
    event, created = collector.collect_manual({"source_id": "manual", "platform": "manual", "text": "BTC attention rising #BTC"})
    duplicate, duplicate_created = collector.collect_manual({"source_id": "manual", "platform": "manual", "text": "BTC attention rising #BTC"})
    assert created is True
    assert duplicate_created is False
    assert event.content_hash == duplicate.content_hash
    assert collector.collect_all_enabled(limit_per_source=1) == []
