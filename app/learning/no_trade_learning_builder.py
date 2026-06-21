from __future__ import annotations

from typing import Any

from app.learning.contracts import NoTradeLearning


class NoTradeLearningBuilder:
    def build(self, log: dict[str, Any], regret: dict[str, Any]) -> NoTradeLearning:
        band = str(regret.get("regret_band") or "INSUFFICIENT_DATA")
        if band == "HIGH_REGRET":
            signal = "loosen_filter" if str(log.get("primary_reason")) not in {"insufficient_data", "stale_data"} else "improve_data"
            suggested = signal
        elif band == "GOOD_NO_TRADE":
            signal = "keep_filter"
            suggested = "keep_filter"
        elif band == "INSUFFICIENT_DATA":
            signal = "improve_data"
            suggested = "improve_data"
        else:
            signal = "keep_filter"
            suggested = "keep_filter"
        return NoTradeLearning(
            no_trade_id=str(log.get("no_trade_id") or regret.get("no_trade_id")),
            market_id=str(log.get("market_id") or regret.get("market_id")),
            market_family=log.get("market_family"),
            candidate_engine=log.get("candidate_engine"),
            regret_band=band,
            regret_score=regret.get("regret_score"),
            learning_signal=signal,
            suggested_filter_change=suggested,
            confidence=float(regret.get("confidence") or 0.0),
            explanation=f"No-trade learning converted regret band {band} into {signal}.",
        )
