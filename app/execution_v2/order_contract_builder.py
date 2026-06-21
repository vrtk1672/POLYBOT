from __future__ import annotations

from typing import Any

from app.execution_v2.contracts import OrderContract


class OrderContractBuilder:
    def build(self, *, market_id: str, strategy_route: dict[str, Any], allocation: dict[str, Any], risk_decision: dict[str, Any], exit_plan_id: str, execution_mode: str, orderbook: dict[str, Any], liquidity: dict[str, Any] | None = None, fee: dict[str, Any] | None = None, dry_run: bool = False) -> OrderContract:
        side = str(strategy_route.get("side") or allocation.get("side") or risk_decision.get("side") or "YES").upper()
        best_bid = float(orderbook.get("best_bid") or 0.0)
        best_ask = float(orderbook.get("best_ask") or 0.0)
        mid = float(orderbook.get("mid_price") or ((best_bid + best_ask) / 2.0 if best_bid and best_ask else 0.0))
        entry_max = strategy_route.get("entry_price_max")
        if entry_max is None:
            entry_max = (strategy_route.get("engine_contract_json") or {}).get("entry_price_max") if isinstance(strategy_route.get("engine_contract_json"), dict) else None
        if side == "YES":
            price = best_ask or mid
            if entry_max is not None:
                price = min(price, float(entry_max))
        else:
            price = best_bid or mid
        size_usd = min(float(allocation.get("approved_size_usd") or allocation.get("requested_size_usd") or strategy_route.get("max_position_size_usd") or 0.0), float(risk_decision.get("approved_position_size_usd") or allocation.get("approved_size_usd") or 0.0) or float(allocation.get("approved_size_usd") or 0.0))
        size = size_usd / price if price > 0 else 0.0
        contract_json = strategy_route.get("engine_contract_json") if isinstance(strategy_route.get("engine_contract_json"), dict) else {}
        cancel_if = contract_json.get("cooldown_triggers") or strategy_route.get("cancel_if_json") or {"spread_widens": 600, "fill_rate_too_low": 0.25, "ttl_expired": True, "slippage_too_high": 250}
        return OrderContract(
            market_id=market_id,
            market_family=strategy_route.get("market_family") or allocation.get("market_family"),
            side=side,
            token_id=orderbook.get("token_id"),
            engine=strategy_route.get("selected_engine") or allocation.get("engine") or risk_decision.get("engine") or "SAFE",
            execution_mode=execution_mode,  # type: ignore[arg-type]
            price=price,
            size=size,
            size_usd=size_usd,
            ttl_seconds=int(strategy_route.get("max_hold_minutes") or contract_json.get("expected_hold_minutes") or 5) * 60,
            max_slippage_bps=float(risk_decision.get("constraints_json", {}).get("max_slippage_bps") if isinstance(risk_decision.get("constraints_json"), dict) else 150.0),
            cancel_if=cancel_if,
            risk_gate_run_id=risk_decision.get("run_id"),
            risk_decision_id=risk_decision.get("id"),
            exit_plan_id=exit_plan_id,
            strategy_route_id=strategy_route.get("id"),
            allocation_id=allocation.get("allocation_id"),
            orderbook_snapshot=orderbook,
            liquidity_snapshot=liquidity or {},
            fee_snapshot=fee or {},
            risk_snapshot=risk_decision,
            dry_run=dry_run,
        )

