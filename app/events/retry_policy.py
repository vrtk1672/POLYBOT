from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: list[int] = field(default_factory=lambda: [5, 30, 120])

    def should_retry(self, attempt_number: int) -> bool:
        return attempt_number < self.max_attempts

    def should_dlq(self, attempt_number: int) -> bool:
        return attempt_number >= self.max_attempts

    def next_retry_at(self, attempt_number: int) -> datetime:
        index = max(0, min(attempt_number - 1, len(self.backoff_seconds) - 1))
        return datetime.now(UTC) + timedelta(seconds=self.backoff_seconds[index])
