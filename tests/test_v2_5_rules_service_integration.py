from __future__ import annotations

from app.data_foundation.market_registry import MarketRegistry
from app.data_foundation.market_rules_store import MarketRulesStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.rules_neuron.service import RulesNeuronService


def test_active_market_rules_analyzed_and_persisted(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": "m1", "question": "Will event be announced before deadline?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    store = MarketRulesStore()
    store.upsert_rules(store.extract_rules({"description": "Resolves if announced before end of day without timezone.", "endDate": "2026-06-01T00:00:00Z"}, market_id="m1"))
    service = RulesNeuronService(connection_factory=DatabaseConnectionFactory())
    result = service.analyze_market_rules("m1")
    assert result.rules_analysis_id
    assert result.wording_risk > 0
    assert result.recommendation in {"PENALIZE_HEAVILY", "NO_TRADE", "REVIEW_REQUIRED"}
    assert service.get_latest_analysis("m1") is not None


def test_missing_rules_creates_no_trade_or_review(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": "m2", "question": "Missing rules?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    result = RulesNeuronService(connection_factory=DatabaseConnectionFactory()).analyze_market_rules("m2")
    assert result.recommendation in {"NO_TRADE", "REVIEW_REQUIRED"}
    assert result.wording_risk >= 0.85

