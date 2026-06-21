from app.capital.reinvest_brain import ReinvestBrain


def test_reinvest_moves_only_realized_profit_to_attack_bank():
    decision = ReinvestBrain().evaluate(realized_profit_usd=100)
    assert decision.allowed is True
    assert decision.amount_usd == 30
    assert decision.from_bucket == "PROFIT_POCKET"
    assert decision.to_bucket == "ATTACK_BANK"
    assert decision.policy["base_capital_allowed"] is False


def test_reinvest_blocks_without_realized_profit_and_dry_run_writes_nothing():
    decision = ReinvestBrain().evaluate(realized_profit_usd=0, dry_run=True)
    assert decision.allowed is False
    assert decision.block_reason == "no_realized_profit"
    assert decision.dry_run is True

