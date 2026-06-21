from __future__ import annotations

from app.execution_v2.contracts import FillRecord, OrderContract


class FailedFillHandler:
    def failed(self, contract: OrderContract, reason: str) -> FillRecord:
        return FillRecord(order_id=contract.order_id, market_id=contract.market_id, side=contract.side, fill_mode="PAPER_SIM", fill_status="FAILED", requested_size=contract.size, filled_size=0, fill_price=0, expected_price=contract.price, slippage_bps=10_000, fill_probability=0, failed_reason=reason)

