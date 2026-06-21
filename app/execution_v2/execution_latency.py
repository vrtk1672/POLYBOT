from __future__ import annotations

from datetime import UTC, datetime


class ExecutionLatencyTracker:
    def measure_ms(self, started_at: datetime, finished_at: datetime | None = None) -> float:
        finished = finished_at or datetime.now(UTC)
        return max(0.0, (finished - started_at).total_seconds() * 1000.0)

