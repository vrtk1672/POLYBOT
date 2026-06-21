from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.social_neuron.price_lead_lag_detector import PriceLeadLagDetector


def test_missing_data_is_insufficient(postgres_test_schema) -> None:
    run_migrations()
    result = PriceLeadLagDetector(connection_factory=DatabaseConnectionFactory()).detect_social_price_lead_lag("missing")
    assert result["lead_lag_status"] == "INSUFFICIENT_DATA"


def test_social_before_price_leads(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    MarketRegistry().upsert_market(MarketRegistry().normalize_market({"id": "m1", "question": "BTC?", "category": "crypto", "clobTokenIds": ["yes", "no"]}))
    now = datetime.now(UTC)
    with factory.connect() as conn:
        conn.execute("INSERT INTO social_normalized_events (social_event_id, source_id, platform, text, normalized_text, collected_at) VALUES ('s1','manual','manual','BTC','btc',%s)", (now - timedelta(minutes=10),))
        conn.execute("INSERT INTO social_market_links (social_link_id, social_event_id, market_id, link_score, confidence) VALUES ('l1','s1','m1',0.8,0.8)")
        conn.execute("INSERT INTO market_snapshots_v2 (snapshot_id, market_id, current_price_yes, snapshot_at) VALUES ('p1','m1',0.4,%s),('p2','m1',0.45,%s)", (now - timedelta(minutes=8), now - timedelta(minutes=2)))
        conn.commit()
    result = PriceLeadLagDetector(connection_factory=factory).detect_social_price_lead_lag("m1")
    assert result["lead_lag_status"] == "SOCIAL_LEADS_PRICE"
