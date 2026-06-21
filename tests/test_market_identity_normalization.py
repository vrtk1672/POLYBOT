from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.market_universe_memory import MarketUniverseMemoryService
from market_memory_helpers import insert_market, setup_market_tables


def test_condition_token_slug_and_title_lookup_work(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("lookup-m", condition_id="lookup-cond", slug="lookup-slug", yes_token_id="lookup-yes")
    service = MarketUniverseMemoryService()
    service.refresh_universe(force=True)

    assert service.lookup(condition_id="lookup-cond")["match"]["market_id"] == "lookup-m"
    assert service.lookup(token_id="lookup-yes")["match"]["market_id"] == "lookup-m"
    assert service.lookup(slug="lookup-slug")["match"]["market_id"] == "lookup-m"
    assert service.lookup(title="Will lookup-m resolve yes?")["match"]["market_id"] == "lookup-m"


def test_missing_market_id_but_known_condition_stores_partial(postgres_test_schema) -> None:
    setup_market_tables()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, condition_id, question, slug, active, closed, archived, accepting_orders)
            VALUES (NULL, 'partial-cond', 'Partial condition?', NULL, true, false, false, true)
            """
        )
    MarketUniverseMemoryService().refresh_universe(force=True)

    match = MarketUniverseMemoryService().lookup(condition_id="partial-cond")["match"]
    assert match["identity_verification_state"] == "PARTIAL"


def test_missing_tokens_and_token_conflict_are_explicit(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("missing-tokens", yes_token_id=None, no_token_id=None)
    insert_market("token-conflict", yes_token_id="same-token", no_token_id="same-token")
    MarketUniverseMemoryService().refresh_universe(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        missing = conn.execute("SELECT token_verification_state FROM market_universe_memory WHERE market_id='missing-tokens'").fetchone()
        conflict = conn.execute("SELECT token_verification_state FROM market_universe_memory WHERE market_id='token-conflict'").fetchone()
    assert missing["token_verification_state"] == "TOKENS_MISSING"
    assert conflict["token_verification_state"] == "TOKENS_MISMATCH"
