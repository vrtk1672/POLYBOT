from app.brains.context_input_builder import ContextInputBuilder


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


def test_context_input_builder_uses_manual_payload_and_marks_missing_memory():
    payload = ContextInputBuilder().build(
        FakeConn(),
        "m1",
        {
            "news_signals": [{"strength": 0.8}],
            "memory_snapshot": {"confidence": 0.4},
            "data_completeness_score": 0.6,
        },
    )

    assert payload.market_id == "m1"
    assert payload.news_signals
    assert payload.data_completeness_score == 0.6
    assert "missing_context_signals" not in payload.insufficient_data_reasons


def test_context_input_builder_marks_insufficient_when_db_has_no_context():
    payload = ContextInputBuilder().build(FakeConn(), "m2")

    assert "missing_market_memory" in payload.insufficient_data_reasons
    assert "missing_context_signals" in payload.insufficient_data_reasons
