from __future__ import annotations

from app.execution_v2.contracts import OrderContract, ShadowExecutionPlan, bounded
from app.execution_v2.slippage_curve import SlippageCurveEstimator


class ShadowExecutionPlanner:
    def __init__(self) -> None:
        self.slippage = SlippageCurveEstimator()

    def plan(self, contract: OrderContract) -> ShadowExecutionPlan:
        depth = float(contract.orderbook_snapshot.get("depth_2c") or contract.orderbook_snapshot.get("depth_5c") or 0.0)
        spread = float(contract.orderbook_snapshot.get("spread_bps") or 0.0)
        expected_slippage = self.slippage.estimate_bps(requested_size=contract.size, available_depth=depth, spread_bps=spread)
        return ShadowExecutionPlan(
            order_id=contract.order_id,
            planned_order=contract.model_dump(mode="json"),
            expected_fill_probability=bounded(depth / contract.size if contract.size else 0),
            expected_slippage_bps=expected_slippage,
            expected_latency_ms=125.0,
            cancel_conditions=contract.cancel_if,
        )

