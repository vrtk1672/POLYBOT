from __future__ import annotations

from typing import Any

from app.exit_cortex.contracts import ExitPlan


class ExitPlanBuilder:
    def build(self, *, market_id: str, order: dict[str, Any] | None = None, strategy_route: dict[str, Any] | None = None, risk_decision: dict[str, Any] | None = None, manual: dict[str, Any] | None = None) -> ExitPlan:
        manual = manual or {}
        order = order or manual.get("order") or {}
        route = strategy_route or manual.get("strategy_route") or {}
        risk = risk_decision or manual.get("risk_decision") or {}
        contract = route.get("engine_contract_json") if isinstance(route.get("engine_contract_json"), dict) else {}
        reasons: list[str] = []
        entry_price = manual.get("entry_price", order.get("avg_fill_price") or order.get("price") or contract.get("entry_price_max") or 0.0)
        entry_size = manual.get("entry_size", order.get("filled_size") or order.get("size") or 0.0)
        target_exit = manual.get("target_exit", route.get("target_exit") or contract.get("target_exit"))
        stop_loss = manual.get("stop_loss", route.get("stop_loss") or contract.get("stop_loss"))
        max_hold_seconds = manual.get("max_hold_seconds", int(float(route.get("max_hold_minutes") or contract.get("expected_hold_minutes") or 0) * 60) or None)
        liquidity_check = manual["liquidity_exit_check"] if "liquidity_exit_check" in manual else {"min_exit_quality": 0.25, "max_slippage_bps": 250, "require_bid_ask": True, "require_depth": True}
        emergency = manual.get("emergency_exit") or {"enabled": True, "risk_governor_blocks": True, "adverse_move_pct": 0.25}
        invalidation = manual.get("invalidation_rule") or {"enabled": True}
        if not target_exit:
            reasons.append("missing_target_exit")
        if stop_loss is None:
            reasons.append("missing_stop_loss")
        if not max_hold_seconds:
            reasons.append("missing_max_hold_seconds")
        if not liquidity_check:
            reasons.append("missing_liquidity_exit_check")
        if not invalidation and not emergency:
            reasons.append("missing_invalidation_or_emergency_condition")
        if not entry_price or not entry_size:
            reasons.append("missing_entry")
        return ExitPlan(
            exit_plan_id=manual.get("exit_plan_id") or order.get("exit_plan_id") or None or f"exit_plan_{market_id}",
            market_id=market_id,
            market_family=manual.get("market_family") or order.get("market_family") or route.get("market_family"),
            side=manual.get("side") or order.get("side") or route.get("side") or "YES",
            engine=manual.get("engine") or order.get("engine") or route.get("selected_engine") or risk.get("engine") or "SAFE",
            strategy_route_id=manual.get("strategy_route_id") or order.get("strategy_route_id") or route.get("id"),
            allocation_id=manual.get("allocation_id") or order.get("allocation_id"),
            risk_gate_run_id=manual.get("risk_gate_run_id") or order.get("risk_gate_run_id") or risk.get("run_id"),
            order_id=manual.get("order_id") or order.get("order_id"),
            position_ref=manual.get("position_ref"),
            entry_price=float(entry_price or 0),
            entry_size=float(entry_size or 0),
            target_exit=float(target_exit) if target_exit is not None else None,
            partial_take_profit=manual.get("partial_take_profit", route.get("partial_take_profit") or contract.get("partial_take_profit")),
            partial_take_profit_pct=manual.get("partial_take_profit_pct", 0.5 if manual.get("partial_take_profit") or route.get("partial_take_profit") else None),
            stop_loss=float(stop_loss) if stop_loss is not None else None,
            max_hold_seconds=int(max_hold_seconds) if max_hold_seconds else None,
            invalidation_rule=invalidation,
            liquidity_exit_check=liquidity_check,
            emergency_exit=emergency,
            momentum_decay_exit=manual.get("momentum_decay_exit") or {"min_momentum": 0.2},
            spread_exit=manual.get("spread_exit") or {"max_spread_bps": 500},
            news_invalidated_exit=manual.get("news_invalidated_exit") or {"enabled": True},
            exit_mode=manual.get("exit_mode") or ("SHADOW_EXIT_PLAN" if str(order.get("execution_mode") or "").upper() == "SHADOW_PLAN" else "PAPER_SIM_EXIT"),
            data_confidence=0.35 if reasons else 0.85,
            insufficient_data=bool(reasons),
            insufficient_data_reasons=reasons,
        )
