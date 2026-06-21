from __future__ import annotations

from app.execution_v2.contracts import FillRecord, OrderContract, bounded
from app.execution_v2.slippage_curve import SlippageCurveEstimator


class FillSimulator:
    def __init__(self) -> None:
        self.slippage = SlippageCurveEstimator()

    def simulate(self, contract: OrderContract) -> FillRecord:
        orderbook = contract.orderbook_snapshot or {}
        liquidity = contract.liquidity_snapshot or {}
        depth = float(orderbook.get("depth_2c") or orderbook.get("depth_5c") or liquidity.get("max_safe_size_contracts") or 0.0)
        spread_bps = float(orderbook.get("spread_bps") or 0.0)
        slippage_bps = self.slippage.estimate_bps(requested_size=contract.size, available_depth=depth, spread_bps=spread_bps)
        if depth <= 0:
            return FillRecord(order_id=contract.order_id, market_id=contract.market_id, side=contract.side, fill_mode="PAPER_SIM", fill_status="FAILED", requested_size=contract.size, filled_size=0, fill_price=0, expected_price=contract.price, slippage_bps=slippage_bps, fill_probability=0, failed_reason="missing_depth")
        if slippage_bps > contract.max_slippage_bps:
            return FillRecord(order_id=contract.order_id, market_id=contract.market_id, side=contract.side, fill_mode="PAPER_SIM", fill_status="FAILED", requested_size=contract.size, filled_size=0, fill_price=0, expected_price=contract.price, slippage_bps=slippage_bps, fill_probability=0.1, failed_reason="slippage_too_high")
        filled = min(contract.size, depth)
        partial = filled < contract.size
        fill_price = contract.price * (1.0 + slippage_bps / 10_000.0)
        if contract.side == "NO":
            fill_price = contract.price * (1.0 - min(slippage_bps, 9999.0) / 10_000.0)
        fee_bps = float(contract.fee_snapshot.get("taker_cost_bps") or contract.fee_snapshot.get("maker_cost_bps") or 0.0)
        return FillRecord(
            order_id=contract.order_id,
            market_id=contract.market_id,
            side=contract.side,
            fill_mode="PAPER_SIM",
            fill_status="PARTIAL" if partial else "FILLED",
            requested_size=contract.size,
            filled_size=filled,
            fill_price=round(fill_price, 6),
            expected_price=contract.price,
            slippage_bps=round(slippage_bps, 4),
            fee_bps=fee_bps,
            fee_usd=round((filled * fill_price) * fee_bps / 10_000.0, 6),
            fill_probability=bounded(depth / contract.size if contract.size else 0),
            liquidity_consumed={"depth_available": depth, "depth_used": filled},
        )

