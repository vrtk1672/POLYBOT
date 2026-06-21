from __future__ import annotations

import pytest

from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.rules_neuron.rules_errors import RulesAnalysisBlocked
from app.rules_neuron.service import RulesNeuronService
from app.runtime.state_governor import StateGovernor


def test_kill_blocks_rules_analysis_jobs(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": "m1", "question": "Blocked?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    governor = StateGovernor(connection_factory=factory)
    governor.ensure_initial_state()
    governor.activate_kill(actor="test", reason="safety")
    with pytest.raises(RulesAnalysisBlocked):
        RulesNeuronService(connection_factory=factory, state_governor=governor).analyze_market_rules("m1")


def test_rules_output_has_no_orders_or_legal_advice() -> None:
    from app.rules_neuron.contracts import RulesAnalysisResult

    result = RulesAnalysisResult(market_id="m1", recommendation="NO_TRADE", cannot_trade_reason="rules missing")
    text = str(result.model_dump()).lower()
    assert "order_intent" not in text
    assert "legal advice" not in text

