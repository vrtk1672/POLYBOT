from __future__ import annotations

import pytest

from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.modes import RuntimeMode
from app.runtime.state_governor import StateGovernor
from app.social_neuron.contracts import SocialPlatform, SocialSource, SocialSourceType
from app.social_neuron.service import SocialNeuronService
from app.social_neuron.social_errors import SocialCollectionBlocked
from app.social_neuron.source_registry import SocialSourceRegistry


def test_kill_blocks_collection_and_no_trade_side_effects(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    SocialSourceRegistry(connection_factory=factory).register_source(SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL))
    StateGovernor(connection_factory=factory).activate_kill(actor="test", reason="social safety")
    with pytest.raises(SocialCollectionBlocked):
        SocialNeuronService(connection_factory=factory).process_manual_social({"source_id": "manual", "platform": "manual", "text": "BTC"})


def test_irrelevant_social_ignored_and_compliance_block_lowers_confidence(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    MarketRegistry().upsert_market(MarketRegistry().normalize_market({"id": "btc-market", "question": "Will BTC close above 100k?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    with factory.connect() as conn:
        conn.execute("INSERT INTO compliance_blocks (compliance_block_id, market_id, block_type, severity, reason) VALUES ('b1','btc-market','MANUAL_BLOCK','BLOCKING','test')")
        conn.commit()
    SocialSourceRegistry(connection_factory=factory).register_source(SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL))
    StateGovernor(connection_factory=factory).request_mode_change(to_mode=RuntimeMode.DATA_ONLY, actor="test", reason="resume")
    service = SocialNeuronService(connection_factory=factory)
    irrelevant = service.process_manual_social({"source_id": "manual", "platform": "manual", "text": "cooking dinner", "category": "general"})
    linked = service.process_manual_social({"source_id": "manual", "platform": "manual", "text": "BTC traders watching #BTC", "category": "crypto"})
    assert irrelevant["link_count"] == 0
    assert linked["links"]
    assert linked["links"][0]["confidence"] < 0.5
