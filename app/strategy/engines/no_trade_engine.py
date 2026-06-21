from __future__ import annotations

from app.strategy.contracts import EngineContract, EngineDecision


class NoTradeEngine:
    name = "NO_TRADE"

    def evaluate(self, payload) -> EngineDecision:
        contract = EngineContract(
            engine=self.name,
            market_id=payload.market_id,
            side=payload.side,
            entry_conditions={"no_entry": True},
            exit_conditions={"no_position": True},
            risk_limits={"max_loss_usd": 0, "max_position_size_usd": 0},
            position_sizing_rules={"position_size_usd": 0, "capital_reserved": False},
            expected_hold_minutes=0,
            entry_price_max=None,
            target_exit=None,
            partial_take_profit=None,
            stop_loss=None,
            max_position_size_usd=0,
            max_loss_usd=0,
            entry_mode="NONE",
            exit_mode="NONE",
            execution_mode="CONTRACT_ONLY",
            reason="NO_TRADE is always valid when engines are rejected or data is unsafe.",
        )
        return EngineDecision(engine=self.name, eligible=True, engine_score=0.01, confidence=1.0, contract=contract)

