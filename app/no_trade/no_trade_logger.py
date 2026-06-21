from __future__ import annotations

from typing import Any

from app.no_trade.candidate_tracker import NoTradeCandidateTracker
from app.no_trade.contracts import NoTradeDecision


class NoTradeLogger:
    def __init__(self, tracker: NoTradeCandidateTracker | None = None) -> None:
        self.tracker = tracker or NoTradeCandidateTracker()

    def build(self, payload: dict[str, Any]) -> NoTradeDecision:
        return self.tracker.build_decision(payload)
