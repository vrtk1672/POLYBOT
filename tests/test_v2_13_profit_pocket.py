from app.capital.profit_pocket_manager import ProfitPocketManager


def test_profit_pocket_grows_only_from_positive_realized_profit():
    result = ProfitPocketManager().update_from_realized_profit(current_available=10, realized_profit_usd=25)
    assert result["available_profit_usd"] == 35
    negative = ProfitPocketManager().update_from_realized_profit(current_available=10, realized_profit_usd=-50)
    assert negative["available_profit_usd"] == 10

