from __future__ import annotations

from app.data_foundation.market_registry import MarketRegistry
from app.data_foundation.market_rules_store import MarketRulesStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.rules_neuron.rules_ingestion import RulesIngestion


def test_rules_loaded_from_data_foundation_hash_stable(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": "m1", "question": "Will BTC?", "category": "crypto", "clobTokenIds": ["yes", "no"]}))
    store = MarketRulesStore()
    store.upsert_rules(store.extract_rules({"description": "Resolve by official source https://sec.gov/x", "endDate": "2026-06-01T00:00:00Z"}, market_id="m1"))
    ingestion = RulesIngestion(connection_factory=DatabaseConnectionFactory())
    rules_input = ingestion.build_rules_input("m1")
    assert rules_input.rules_text
    assert ingestion.compute_rules_hash("x", "y", "z") == ingestion.compute_rules_hash("x", "y", "z")


def test_missing_rules_handled(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": "m2", "question": "Missing rules?", "category": "crypto", "clobTokenIds": ["yes", "no"]}))
    rules_input = RulesIngestion(connection_factory=DatabaseConnectionFactory()).build_rules_input("m2")
    assert rules_input.rules_text is None
    assert rules_input.metadata["rules_missing"] is True

