from __future__ import annotations

from app.execution_v2.contracts import OrderStatus


class OrderLifecycleManager:
    def created_status(self, execution_mode: str) -> OrderStatus:
        if execution_mode == "SHADOW_PLAN":
            return "PLANNED_SHADOW"
        return "SUBMITTED_PAPER"

    def status_from_fill(self, *, filled_size: float, remaining_size: float, failed: bool = False) -> OrderStatus:
        if failed and filled_size <= 0:
            return "FAILED"
        if remaining_size <= 0 and filled_size > 0:
            return "FILLED"
        if filled_size > 0:
            return "PARTIALLY_FILLED"
        return "FAILED"

