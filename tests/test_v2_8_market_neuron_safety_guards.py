from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.market_neuron.service import MarketNeuronService
from app.market_neuron.technical_errors import MarketNeuronBlocked


class BlockingGovernor:
    def assert_can_execute(self, action):
        raise RuntimeError("blocked")


def test_market_neuron_cannot_create_orders_or_order_intents(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    before = {}
    with factory.connect() as conn:
        for table in ("orders", "order_intents", "live_orders", "paper_orders", "exit_intents"):
            exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
            if exists:
                before[table] = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
    MarketNeuronService(connection_factory=factory).analyze_market("safe", raw_market_snapshot={"current_price_yes": 0.5}, raw_orderbook={})
    with factory.connect() as conn:
        for table, count in before.items():
            assert conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] == count


def test_kill_style_block_blocks_analysis_jobs(postgres_test_schema):
    run_migrations()
    service = MarketNeuronService(connection_factory=DatabaseConnectionFactory(), state_governor=BlockingGovernor())
    try:
        service.analyze_market("blocked")
    except MarketNeuronBlocked:
        pass
    else:
        raise AssertionError("analysis should be blocked")

