from app.strategy.contracts import StrategyRouteInput
from app.strategy.engine_contract_builder import EngineContractBuilder


def test_every_non_no_trade_contract_has_required_contract_fields():
    payload = StrategyRouteInput(
        market_id="m1",
        side="YES",
        opportunity_score=0.8,
        opportunity_components={"price_yes": 0.42, "max_safe_size_usd": 1000},
        capital_output={"max_position_size_usd": 200},
    )
    contract = EngineContractBuilder().build(payload, engine="SAFE", reason="test", entry_mode="LIMIT_CONTRACT", exit_mode="TARGET_STOP_CONTRACT", max_hold_minutes=60)
    assert contract.market_id == "m1"
    assert contract.engine == "SAFE"
    assert contract.entry_price_max is not None
    assert contract.target_exit is not None
    assert contract.stop_loss is not None
    assert contract.max_loss_usd >= 0
    assert contract.execution_mode == "CONTRACT_ONLY"
    assert contract.position_sizing_rules["no_capital_reserved"] is True

