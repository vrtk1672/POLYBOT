from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.news_neuron.collector import NewsCollector
from app.news_neuron.contracts import NewsSource, NewsSourceType
from app.news_neuron.source_registry import NewsSourceRegistry


def test_manual_item_collected_and_duplicate_not_duplicated(postgres_test_schema) -> None:
    run_migrations()
    collector = NewsCollector(connection_factory=DatabaseConnectionFactory())
    payload = {"source_id": "manual", "title": "BTC test headline", "summary": "same"}
    first, created_first = collector.collect_manual(payload)
    second, created_second = collector.collect_manual(payload)
    assert created_first is True
    assert created_second is False
    assert first.content_hash == second.content_hash


def test_mocked_rss_item_collected_and_bad_source_does_not_block_others(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    registry = NewsSourceRegistry(connection_factory=factory)
    registry.register_source(NewsSource(source_id="rss", name="RSS", source_type=NewsSourceType.RSS, feed_url="https://example.test/feed", enabled=True))
    xml = "<rss><channel><item><title>BTC RSS headline</title><link>https://x.test/a</link><description>summary</description></item></channel></rss>"
    collector = NewsCollector(connection_factory=factory, fetch_text=lambda url: xml)
    items = collector.collect_from_source("rss")
    assert len(items) == 1
    assert items[0].title == "BTC RSS headline"

