from app.capital.attack_bank_manager import AttackBankManager


def test_attack_bank_cannot_use_base_reserve():
    result = AttackBankManager().move_from_profit(current_available=0, profit_available=100)
    assert result["available_usd"] == 30
    assert result["base_capital_used_usd"] == 0

