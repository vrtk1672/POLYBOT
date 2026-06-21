from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.contracts import SocialPlatform, SocialSource, SocialSourceType
from app.social_neuron.source_registry import DEFAULT_CATEGORIES, SocialSourceRegistry


def test_source_registered_enabled_disabled_and_fetch_status(postgres_test_schema) -> None:
    run_migrations()
    registry = SocialSourceRegistry(connection_factory=DatabaseConnectionFactory())
    source = SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL, metadata={"api_key": "secret"})
    _, created = registry.register_source(source)
    _, created_again = registry.register_source(source)
    registry.disable_source("manual")
    assert registry.get_source("manual")["enabled"] is False
    registry.enable_source("manual")
    registry.update_fetch_status("manual", success=False, error_message="boom")
    row = registry.get_source("manual")
    assert created is True
    assert created_again is False
    assert row["enabled"] is True
    assert row["error_count"] == 1
    assert row["metadata_json"]["api_key"] == "[REDACTED]"
    assert "crypto" in DEFAULT_CATEGORIES
