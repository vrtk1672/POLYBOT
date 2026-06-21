from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.opportunity.signal_input_builder import OpportunitySignalInputBuilder


def test_signal_input_builder_uses_manual_payload():
    class FakeConn:
        def execute(self, query, params=None):
            class Result:
                def fetchone(self_inner):
                    if "to_regclass" in query:
                        return {"name": None}
                    return None

                def fetchall(self_inner):
                    return []

            return Result()

    payload = OpportunitySignalInputBuilder().build(
        FakeConn(),
        "m1",
        manual={
            "context_output": {"strength": 0.8, "confidence": 0.8},
            "capital_output": {"capital_allowed": True, "allocation_confidence": 0.8},
            "market_memory": {"memory_confidence": 0.7},
            "data_completeness_score": 0.9,
        },
    )

    assert payload.market_id == "m1"
    assert payload.data_completeness_score == 0.9
    assert "missing_context_output" not in payload.insufficient_data_reasons


def test_signal_input_builder_marks_missing_db_data(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        payload = OpportunitySignalInputBuilder().build(conn, "missing")

    assert "missing_context_output" in payload.insufficient_data_reasons
    assert "missing_capital_output" in payload.insufficient_data_reasons

