from __future__ import annotations

from app.execution_v2.contracts import ExecutionQualityResult, FillRecord, bounded


class ExecutionQualityScorer:
    def score(self, *, order_id: str, market_id: str, expected_price: float, expected_slippage_bps: float, expected_fill_probability: float, requested_size: float, fills: list[FillRecord], cancelled: bool = False) -> ExecutionQualityResult:
        filled = sum(fill.filled_size for fill in fills)
        fill_ratio = filled / requested_size if requested_size > 0 else 0.0
        failed_count = sum(1 for fill in fills if fill.fill_status == "FAILED")
        partial_count = sum(1 for fill in fills if fill.partial)
        actual_price = None
        actual_slippage = None
        if filled > 0:
            actual_price = sum(fill.fill_price * fill.filled_size for fill in fills) / filled
            actual_slippage = sum(fill.slippage_bps * fill.filled_size for fill in fills) / filled
        flags: list[str] = []
        if fill_ratio < 1.0:
            flags.append("partial_or_unfilled")
        if failed_count:
            flags.append("failed_fill")
        if cancelled:
            flags.append("cancelled")
        if actual_slippage is not None and actual_slippage > expected_slippage_bps:
            flags.append("slippage_worse_than_expected")
        score = bounded((0.55 * fill_ratio) + (0.30 * expected_fill_probability) + (0.15 * max(0.0, 1.0 - (expected_slippage_bps / 1000.0))))
        if failed_count:
            score *= 0.35
        if cancelled:
            score *= 0.75
        return ExecutionQualityResult(
            order_id=order_id,
            market_id=market_id,
            expected_fill_price=expected_price,
            actual_fill_price=actual_price,
            expected_slippage_bps=expected_slippage_bps,
            actual_slippage_bps=actual_slippage,
            expected_fill_probability=expected_fill_probability,
            actual_fill_ratio=fill_ratio,
            cancel_count=1 if cancelled else 0,
            failed_fill_count=failed_count,
            partial_fill_count=partial_count,
            execution_quality_score=round(score, 4),
            quality_flags=flags,
        )

