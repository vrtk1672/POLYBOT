from __future__ import annotations

from app.data_foundation.market_registry import MarketRegistry
from app.data_foundation.market_snapshotter_v2 import MarketSnapshotterV2
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.news_neuron.contracts import NewsSource, NewsSourceType
from app.news_neuron.service import NewsNeuronService
from app.news_neuron.source_registry import NewsSourceRegistry


def _seed_market() -> None:
    registry = MarketRegistry()
    record = registry.normalize_market({"id": "btc-market", "question": "Will BTC close above 100k?", "category": "crypto", "active": True, "acceptingOrders": True, "clobTokenIds": ["yes", "no"]})
    registry.upsert_market(record)
    snapshot = MarketSnapshotterV2().build_snapshot_from_market({"market_id": "btc-market", "question": "Will BTC close above 100k?", "yes_price": 0.5, "yes_token_id": "yes", "no_token_id": "no", "accepting_orders": True, "closed": False, "time_to_close_seconds": 3600})
    MarketSnapshotterV2().persist_snapshot(snapshot)


def test_manual_news_goes_through_full_pipeline(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    NewsSourceRegistry(connection_factory=factory).register_source(NewsSource(source_id="manual", name="Manual", source_type=NewsSourceType.MANUAL, category="crypto"))
    _seed_market()
    summary = NewsNeuronService(connection_factory=factory).process_manual_news({"source_id": "manual", "title": "Breaking BTC move toward 100k", "summary": "BTC market related", "category": "crypto"})
    assert summary["normalized_event_id"]
    assert summary["dedup_group_id"]
    assert summary["link_count"] >= 1
    assert summary["impact_count"] >= 1

