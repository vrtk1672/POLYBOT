from __future__ import annotations

from app.execution_v2.execution_quality import ExecutionQualityScorer
from app.execution_v2.contracts import FillRecord


def test_execution_quality_score_recorded():
    fill = FillRecord(order_id="o1", market_id="m1", side="YES", fill_mode="PAPER_SIM", fill_status="FILLED", requested_size=10, filled_size=10, fill_price=0.51, expected_price=0.50, slippage_bps=20, fill_probability=1)
    quality = ExecutionQualityScorer().score(order_id="o1", market_id="m1", expected_price=0.50, expected_slippage_bps=20, expected_fill_probability=1, requested_size=10, fills=[fill])
    assert quality.execution_quality_score > 0.8

