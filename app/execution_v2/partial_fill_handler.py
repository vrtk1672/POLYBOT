from __future__ import annotations

from app.execution_v2.contracts import ExecutionOrderState, FillRecord


class PartialFillHandler:
    def apply(self, *, order_id: str, requested_size: float, fills: list[FillRecord]) -> ExecutionOrderState:
        filled = sum(fill.filled_size for fill in fills)
        remaining = max(0.0, requested_size - filled)
        avg = None if filled <= 0 else sum(fill.fill_price * fill.filled_size for fill in fills) / filled
        status = "FILLED" if remaining <= 0 else "PARTIALLY_FILLED" if filled > 0 else "FAILED"
        return ExecutionOrderState(order_id=order_id, order_status=status, filled_size=filled, remaining_size=remaining, avg_fill_price=avg)

