from __future__ import annotations

from typing import Any

from app.market_memory.contracts import SlippageMemory, avg, bounded


class SlippageMemoryBuilder:
    def build(self, rows: list[dict[str, Any]], *, market_id: str | None = None, market_family: str | None = None, token_id: str | None = None, side: str | None = None) -> SlippageMemory:
        expected = avg([row.get("expected_slippage_bps") for row in rows])
        realized = avg([row.get("realized_slippage_bps") for row in rows])
        error = None if expected is None or realized is None else realized - expected
        failed_fill_rate = _rate([row.get("fill_failed") for row in rows])
        risk = bounded(((expected or 0) / 500) * 0.25 + (abs(error or 0) / 500) * 0.25 + failed_fill_rate * 0.5)
        return SlippageMemory(
            market_id=market_id,
            market_family=market_family,
            token_id=token_id,
            side=side,
            observations_count=len(rows),
            avg_expected_slippage_bps=expected,
            avg_realized_slippage_bps=realized,
            slippage_error_bps=error,
            failed_fill_rate=failed_fill_rate,
            slippage_risk_score=risk,
            confidence=bounded(len(rows) / 20),
            summary={"source": "v2.9", "expected_only": realized is None},
        )


def _rate(values: list[Any]) -> float:
    return 0.0 if not values else bounded(sum(1 for value in values if bool(value)) / len(values))
