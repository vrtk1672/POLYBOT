from app.brains.capital_input_builder import CapitalInputBuilder


class FakeConn:
    def execute(self, query, params=None):
        class Result:
            def fetchone(self_inner):
                return {"name": None} if "to_regclass" in query else None

            def fetchall(self_inner):
                return []

        return Result()


def test_capital_input_builder_uses_explicit_safe_test_payload():
    payload = CapitalInputBuilder().build(
        FakeConn(),
        market_id="m1",
        candidate_engine="strike",
        manual={
            "balance": 1000,
            "available_capital": 800,
            "engine_budgets": {"strike": 100},
            "risk_limits": {"min_cash_reserve_pct": 0.2},
        },
    )

    assert payload.market_id == "m1"
    assert payload.available_capital == 800
    assert payload.engine_budgets["strike"] == 100


def test_capital_input_builder_marks_missing_capital_without_snapshot():
    payload = CapitalInputBuilder().build(FakeConn(), market_id="m1", candidate_engine="safe", connection_factory=None)

    assert payload.available_capital is None
    assert "missing_capital_snapshot" in payload.insufficient_data_reasons
