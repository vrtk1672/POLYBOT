import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.market_memory.memory_errors import MarketMemoryBlocked
from app.market_memory.service import MarketMemoryService


class BlockingGovernor:
    def assert_can_execute(self, action):
        raise RuntimeError("blocked")


def test_market_memory_cannot_create_orders_order_intents_or_exits(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    before = {}
    with factory.connect() as conn:
        for table in ("orders", "order_intents", "live_orders", "paper_orders", "exit_intents"):
            exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
            if exists:
                before[table] = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]

    MarketMemoryService(connection_factory=factory).rebuild(market_id="safe_missing", dry_run=False)

    with factory.connect() as conn:
        for table, count in before.items():
            assert conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] == count


def test_kill_style_block_blocks_memory_rebuild(postgres_test_schema):
    run_migrations()
    service = MarketMemoryService(connection_factory=DatabaseConnectionFactory(), state_governor=BlockingGovernor())

    with pytest.raises(MarketMemoryBlocked):
        service.rebuild(market_id="blocked", dry_run=False)


def test_memory_payloads_do_not_expose_secrets(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    result = MarketMemoryService(connection_factory=factory).rebuild(market_id="redaction_safe", dry_run=False)
    text = str(result).lower()

    assert "api_key" not in text
    assert "private_key" not in text
    assert "secret" not in text
