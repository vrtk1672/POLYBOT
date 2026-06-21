from pathlib import Path

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.learning.service import LearningService
from test_v2_19_fixtures import completed_trade_payload


ROOT = Path(__file__).resolve().parents[1]


def test_migration_does_not_create_order_or_intent_tables():
    text = (ROOT / "app" / "db" / "migrations" / "0056_v2_19_feedback_learning_loop.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists orders" not in text
    assert "create table if not exists order_intents" not in text
    assert "create table if not exists live_orders" not in text
    assert "external balance" not in text


def test_learning_service_does_not_create_orders_or_mutate_balances(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "orders_v2": conn.execute("SELECT COUNT(*) AS count FROM orders_v2").fetchone()["count"],
            "exit_intents": conn.execute("SELECT COUNT(*) AS count FROM exit_intents").fetchone()["count"],
        }
    LearningService().review_trade(completed_trade_payload(), dry_run=False)
    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "orders_v2": conn.execute("SELECT COUNT(*) AS count FROM orders_v2").fetchone()["count"],
            "exit_intents": conn.execute("SELECT COUNT(*) AS count FROM exit_intents").fetchone()["count"],
        }
    assert before == after


def test_model_adjustments_are_recommendation_only():
    result = LearningService().review_trade(completed_trade_payload(entry_price=0.57, exit_price=0.42), dry_run=True)
    for adjustment in result["model_adjustments"]:
        assert adjustment["status"] in {"RECOMMENDED", "REVIEW_REQUIRED"}
        assert adjustment.get("applied_at") is None
