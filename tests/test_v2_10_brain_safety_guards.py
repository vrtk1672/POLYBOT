import pytest

from app.brains.brain_errors import BrainAnalysisBlocked
from app.brains.service import BrainService
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


class BlockingGovernor:
    def assert_can_execute(self, action):
        raise RuntimeError("blocked")

    def get_current_state(self):
        raise RuntimeError("blocked")


def test_brains_create_no_orders_order_intents_exits_or_balance_mutations(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    before = {}
    with factory.connect() as conn:
        for table in ("orders", "order_intents", "live_orders", "paper_orders", "exit_intents", "paper_positions"):
            exists = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"]
            if exists:
                before[table] = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]

    service = BrainService(connection_factory=factory)
    service.analyze_both(
        "safe",
        candidate_engine="strike",
        manual_context={"news_signals": [{"strength": 0.8}], "data_completeness_score": 1.0},
        manual_capital={"balance": 1000, "available_capital": 800, "engine_budgets": {"strike": 100}, "risk_limits": {"min_cash_reserve_pct": 0.2}},
    )

    with factory.connect() as conn:
        for table, count in before.items():
            assert conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] == count


def test_kill_style_block_blocks_brain_analysis(postgres_test_schema):
    run_migrations()
    service = BrainService(connection_factory=DatabaseConnectionFactory(), state_governor=BlockingGovernor())

    with pytest.raises(BrainAnalysisBlocked):
        service.analyze_context("blocked")


def test_ai_context_cannot_override_risk(postgres_test_schema):
    run_migrations()
    output = BrainService(connection_factory=DatabaseConnectionFactory()).analyze_context(
        "risk",
        dry_run=True,
        manual_input={
            "news_signals": [{"strength": 0.9, "confidence": 0.9}],
            "memory_snapshot": {"confidence": 0.8, "rules_risk_memory": [{"rules_risk_score": 0.95}]},
            "ai_analysis": {"summary": "AI says trade"},
            "data_completeness_score": 1.0,
        },
    )["output"]

    assert "ai_cannot_override_risk" in output["risks"]
    assert "api_key" not in str(output).lower()
