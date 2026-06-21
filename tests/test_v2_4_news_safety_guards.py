from __future__ import annotations

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.news_neuron.contracts import NewsSignal
from app.news_neuron.news_errors import NewsCollectionBlocked
from app.news_neuron.service import NewsNeuronService
from app.runtime.state_governor import StateGovernor


def test_news_signal_has_no_order_fields() -> None:
    signal = NewsSignal(market_id="m1", direction="UNKNOWN")
    assert "order" not in signal.model_dump()


def test_kill_blocks_collection(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    governor = StateGovernor(connection_factory=factory)
    governor.ensure_initial_state()
    governor.activate_kill(actor="test", reason="safety")
    service = NewsNeuronService(connection_factory=factory, state_governor=governor)
    with pytest.raises(NewsCollectionBlocked):
        service.process_manual_news({"source_id": "manual", "title": "Should be blocked", "reason": "test"})

