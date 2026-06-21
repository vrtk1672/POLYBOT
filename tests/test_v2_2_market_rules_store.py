from __future__ import annotations

from app.data_foundation.market_rules_store import MarketRulesStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_rules_saved_and_hash_stable(postgres_test_schema) -> None:
    run_migrations()
    store = MarketRulesStore()
    record = store.extract_rules({"description": "Resolve yes if true", "resolutionSource": "official"}, market_id="m1")
    assert record.rules_hash == store.compute_rules_hash("Resolve yes if true", "official", None)
    _row, changed = store.upsert_rules(record)
    assert changed is True
    assert store.get_rules("m1")["rules_text"] == "Resolve yes if true"


def test_changed_rules_updates_and_emits_event(postgres_test_schema) -> None:
    run_migrations()
    store = MarketRulesStore()
    store.upsert_rules(store.extract_rules({"description": "old"}, market_id="m1"))
    _row, changed = store.upsert_rules(store.extract_rules({"description": "new"}, market_id="m1"))
    assert changed is True
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM event_log WHERE event_type='rules.snapshot.created'").fetchone()["count"]
    assert count == 2


def test_missing_rules_tracked(postgres_test_schema) -> None:
    run_migrations()
    store = MarketRulesStore()
    record = store.extract_rules({}, market_id="m1")
    store.upsert_rules(record)
    row = store.get_rules("m1")
    assert row["rules_text"] is None
    assert "rules_missing" in row["ambiguity_flags_json"]
