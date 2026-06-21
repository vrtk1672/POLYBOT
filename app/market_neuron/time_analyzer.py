from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.market_neuron.contracts import TimeSignal, bounded


class TimeAnalyzer:
    def analyze(self, market_id: str, *, snapshot: dict[str, Any] | None = None, market_close_time: datetime | None = None) -> TimeSignal:
        now = datetime.now(UTC)
        close_time = market_close_time or _dt((snapshot or {}).get("market_close_time") or (snapshot or {}).get("end_date") or (snapshot or {}).get("close_time"))
        if close_time:
            seconds = max(0, int((close_time - now).total_seconds()))
        else:
            raw_seconds = (snapshot or {}).get("time_to_close_seconds")
            seconds = None if raw_seconds is None else max(0, int(float(raw_seconds)))
        expected_hold = seconds if seconds is not None else 0
        urgency = 0.0 if seconds is None else bounded(1 - seconds / 86400)
        lockup = 0.0 if seconds is None else bounded(seconds / (30 * 86400))
        efficiency = bounded((urgency * 0.45) + ((1 - lockup) * 0.55))
        ttl_bucket = "unknown"
        if seconds is not None:
            ttl_bucket = "expired" if seconds == 0 else "short" if seconds < 1800 else "medium" if seconds < 86400 else "long"
        block = "market_closed_or_expired" if seconds == 0 else None
        return TimeSignal(
            market_id=market_id,
            market_close_time=close_time,
            time_to_close_seconds=seconds,
            expected_hold_seconds=expected_hold,
            lockup_penalty_score=lockup,
            urgency_score=urgency,
            roi_per_hour_reference=None if seconds in (None, 0) else 3600 / max(seconds, 1),
            time_efficiency_score=efficiency,
            ttl_bucket=ttl_bucket,
            block_reason=block,
        )


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None

