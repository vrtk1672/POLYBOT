from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.services.market_universe_memory import MarketUniverseMemoryService
from market_memory_helpers import insert_market, setup_market_tables


def test_closed_markets_are_archived_not_deleted(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("closed-m", active=False, closed=True, archived=True)

    MarketUniverseMemoryService().refresh_universe(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT status, research_priority FROM market_universe_memory WHERE market_id='closed-m'").fetchone()
    assert row["status"] in {"CLOSED", "ARCHIVED"}
    assert row["research_priority"] == "ARCHIVED"


def test_stale_markets_are_marked_stale_not_removed(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("stale-m", last_seen_at=datetime.now(UTC) - timedelta(days=3), with_snapshot=False)

    MarketUniverseMemoryService().refresh_universe(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT freshness_state FROM market_universe_memory WHERE market_id='stale-m'").fetchone()
    assert row["freshness_state"] == "STALE"


def test_universe_refresh_does_not_create_candidates_or_paper_artifacts(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("safe-m")
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("CREATE TABLE paper_intents (id BIGSERIAL PRIMARY KEY)")
        conn.execute("CREATE TABLE paper_orders (id BIGSERIAL PRIMARY KEY)")
        conn.execute("CREATE TABLE paper_fills (id BIGSERIAL PRIMARY KEY)")
        conn.execute("CREATE TABLE paper_positions (id BIGSERIAL PRIMARY KEY)")
        before = {table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions")}
        candidates_table = conn.execute("SELECT to_regclass('paper_eligibility_candidates') AS reg").fetchone()["reg"]
        candidates_before = conn.execute("SELECT COUNT(*) AS count FROM paper_eligibility_candidates").fetchone()["count"] if candidates_table else None

    MarketUniverseMemoryService().refresh_universe(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        after = {table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions")}
        candidates_table = conn.execute("SELECT to_regclass('paper_eligibility_candidates') AS reg").fetchone()["reg"]
        candidates_after = None
        if candidates_table:
            candidates_after = conn.execute("SELECT COUNT(*) AS count FROM paper_eligibility_candidates").fetchone()["count"]
    assert after == before
    assert candidates_after == candidates_before


def test_research_priority_is_deterministic(postgres_test_schema) -> None:
    setup_market_tables()
    insert_market("priority-m")

    MarketUniverseMemoryService().refresh_universe(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT research_priority FROM market_universe_memory WHERE market_id='priority-m'").fetchone()
    assert row["research_priority"] == "HIGH"
