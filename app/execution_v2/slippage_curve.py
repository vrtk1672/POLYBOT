from __future__ import annotations


class SlippageCurveEstimator:
    def estimate_bps(self, *, requested_size: float, available_depth: float, spread_bps: float) -> float:
        if requested_size <= 0:
            return 0.0
        if available_depth <= 0:
            return 10_000.0
        pressure = max(0.0, requested_size / available_depth - 1.0)
        return max(0.0, float(spread_bps or 0.0)) + pressure * 500.0

