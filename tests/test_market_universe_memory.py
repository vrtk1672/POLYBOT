from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.market_universe_memory import MarketUniverseMemoryService
from market_memory_helpers import insert_market, setup_market_tables


def test_market_memory_upserts_new_active_markets(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("m-1")

    result = MarketUniverseMemoryService().refresh_universe(force=True)

    assert result["status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM market_universe_memory WHERE market_id='m-1'").fetchone()
    assert row["status"] == "ACTIVE"
    assert row["identity_verification_state"] == "VERIFIED"
    assert row["token_verification_state"] == "TOKENS_VERIFIED"


def test_existing_market_updates_without_duplicates(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("m-dup", slug="old-slug")
    service = MarketUniverseMemoryService()
    service.refresh_universe(force=True)
    insert_market("m-dup", slug="new-slug")

    service.refresh_universe(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM market_universe_memory WHERE market_id='m-dup'").fetchone()["count"]
        row = conn.execute("SELECT slug FROM market_universe_memory WHERE market_id='m-dup'").fetchone()
    assert count == 1
    assert row["slug"] == "new-slug"
