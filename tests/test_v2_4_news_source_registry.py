from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.news_neuron.contracts import NewsSource, NewsSourceType
from app.news_neuron.source_registry import DEFAULT_SOURCE_CATEGORIES, NewsSourceRegistry


def test_source_registered_once_enable_disable_and_fetch_status(postgres_test_schema) -> None:
    run_migrations()
    registry = NewsSourceRegistry(connection_factory=DatabaseConnectionFactory())
    source = NewsSource(source_id="manual", name="Manual", source_type=NewsSourceType.MANUAL, category="general")
    first = registry.register_source(source)
    second = registry.register_source(source)
    assert first["source_id"] == second["source_id"]
    registry.disable_source("manual")
    assert registry.get_source("manual")["enabled"] is False
    registry.enable_source("manual")
    registry.update_fetch_status("manual", success=False, error_message="test")
    assert registry.get_source("manual")["error_count"] == 1


def test_default_categories_exist() -> None:
    assert {"crypto", "politics", "sports", "legal", "polymarket"}.issubset(set(DEFAULT_SOURCE_CATEGORIES))

