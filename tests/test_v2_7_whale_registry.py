from app.db.migrate import run_migrations
from app.whale_neuron.contracts import WhaleEvent
from app.whale_neuron.registry import WhaleRegistry


def test_whale_registry_registers_and_updates_totals(postgres_test_schema):
    run_migrations()
    registry = WhaleRegistry()
    event = WhaleEvent(source_id="manual", whale_id="w1", wallet_address="0xabc", size_usd=12000)
    first = registry.upsert_whale(event)
    second = registry.upsert_whale(event)
    assert first["first_seen_at"] == second["first_seen_at"]
    assert second["total_events"] >= 2
    assert registry.get_whale("w1")["whale_id"] == "w1"

