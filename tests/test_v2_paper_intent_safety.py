from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_eligible_candidate


def test_paper_intent_safety_creates_no_executable_artifacts(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_eligible_candidate("safety")

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM positions").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM fills_v2").fetchone()["count"] == 0
        if conn.execute("SELECT to_regclass('order_intents') AS table_name").fetchone()["table_name"]:
            assert conn.execute("SELECT COUNT(*) AS count FROM order_intents").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_intents WHERE execution_allowed=true OR live=true OR order_intent_created=true").fetchone()["count"] == 0
