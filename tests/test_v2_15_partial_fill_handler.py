from __future__ import annotations

from app.execution_v2.contracts import FillRecord
from app.execution_v2.partial_fill_handler import PartialFillHandler


def test_partial_fill_handled():
    fill = FillRecord(order_id="o1", market_id="m1", side="YES", fill_mode="PAPER_SIM", fill_status="PARTIAL", requested_size=10, filled_size=4, fill_price=0.5, expected_price=0.5, slippage_bps=0)
    state = PartialFillHandler().apply(order_id="o1", requested_size=10, fills=[fill])
    assert state.order_status == "PARTIALLY_FILLED"
    assert state.remaining_size == 6

