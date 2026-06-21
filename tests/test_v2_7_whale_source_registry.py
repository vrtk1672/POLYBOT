from app.db.migrate import run_migrations
from app.whale_neuron.contracts import WhaleSource, WhaleSourceType
from app.whale_neuron.source_registry import WhaleSourceRegistry


def test_source_registry_registers_once_and_updates_status(postgres_test_schema):
    run_migrations()
    registry = WhaleSourceRegistry()
    source = WhaleSource(source_id="manual", name="Manual", source_type=WhaleSourceType.MANUAL, metadata={"api_key": "secret"})
    registry.register_source(source)
    registry.register_source(source)
    registry.disable_source("manual")
    registry.enable_source("manual")
    registry.update_fetch_status("manual", success=False, error="boom")
    rows = registry.list_sources(source_type="MANUAL")
    assert len(rows) == 1
    assert rows[0]["enabled"] is True
    assert rows[0]["reliability_score"] == 0.5
    assert "secret" not in str(rows[0]["metadata_json"])
    assert "manual" in WhaleSourceRegistry.DEFAULT_SOURCE_TYPES

