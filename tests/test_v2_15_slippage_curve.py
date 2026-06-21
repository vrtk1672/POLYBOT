from __future__ import annotations

from app.execution_v2.slippage_curve import SlippageCurveEstimator


def test_slippage_curve_penalizes_low_depth():
    curve = SlippageCurveEstimator()
    assert curve.estimate_bps(requested_size=100, available_depth=10, spread_bps=20) > curve.estimate_bps(requested_size=10, available_depth=100, spread_bps=20)

