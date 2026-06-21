from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.learning.service import LearningService
from test_v2_19_fixtures import completed_trade_payload, incomplete_trade_payload


def test_service_dry_run_writes_nothing():
    result = LearningService().review_trade(completed_trade_payload(), dry_run=True)
    assert result["written"] is False
    assert result["review"]["review_status"] == "REVIEWED"


def test_service_persists_learning_records(postgres_test_schema):
    run_migrations()
    result = LearningService().review_trade(completed_trade_payload(), dry_run=False)
    assert result["written"] is True
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("trade_reviews", "signal_performance", "engine_learning", "source_learning", "whale_learning", "ai_learning", "model_adjustments")
        }
    assert counts["trade_reviews"] == 1
    assert counts["signal_performance"] == 1
    assert counts["engine_learning"] == 1
    assert counts["source_learning"] == 1
    assert counts["whale_learning"] == 1
    assert counts["ai_learning"] == 1
    assert counts["model_adjustments"] >= 0


def test_service_handles_missing_completed_trade_honestly(postgres_test_schema):
    run_migrations()
    result = LearningService().review_trade(incomplete_trade_payload(), dry_run=False)
    assert result["review"]["insufficient_data"] is True
    assert result["review"]["review_status"] in {"PENDING", "INSUFFICIENT_DATA"}


def test_service_persists_no_trade_learning(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO no_trade_log (no_trade_id, market_id, source_layer, decision_status, primary_reason, explanation)
            VALUES ('nt_learning_1', '2169995', 'risk', 'BLOCKED', 'governor_block', 'risk block')
            """
        )
        conn.execute(
            """
            INSERT INTO no_trade_regret_score (regret_id, no_trade_id, market_id, regret_score, regret_band, confidence, learning_signal, explanation)
            VALUES ('regret_learning_1', 'nt_learning_1', '2169995', 0.9, 'HIGH_REGRET', 0.8, 'loosen_filter', 'evidence')
            """
        )
    result = LearningService().review_no_trade("nt_learning_1", dry_run=False)
    assert result["written"] is True
    with factory.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM no_trade_learning").fetchone()["count"]
    assert count == 1


def test_service_dedupes_no_trade_rebuild(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            "INSERT INTO no_trade_log (no_trade_id, market_id, source_layer, decision_status, primary_reason, explanation) VALUES ('nt_rebuild_1', '2169995', 'strategy', 'NO_TRADE', 'low_edge', 'low edge')"
        )
        conn.execute(
            "INSERT INTO no_trade_regret_score (regret_id, no_trade_id, market_id, regret_score, regret_band, confidence, learning_signal, explanation) VALUES ('regret_rebuild_1', 'nt_rebuild_1', '2169995', 0.1, 'GOOD_NO_TRADE', 0.8, 'keep_filter', 'good refusal')"
        )
    first = LearningService().rebuild(dry_run=False, scope="no_trade")
    second = LearningService().rebuild(dry_run=False, scope="no_trade")
    assert first["candidates"] == 1
    assert second["candidates"] == 1
    with factory.connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM no_trade_learning WHERE no_trade_id='nt_rebuild_1'").fetchone()["count"]
    assert count == 1
