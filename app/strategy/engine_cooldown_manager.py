from __future__ import annotations

from datetime import UTC, datetime, timedelta


class EngineCooldownManager:
    def cooldown_for_rejections(self, rejections: list[dict], *, minutes: int = 30) -> dict | None:
        blocking = [item for item in rejections if item.get("hard_block")]
        if len(blocking) < 3:
            return None
        now = datetime.now(UTC)
        return {
            "engine": "ALL_TRADE_ENGINES",
            "market_id": blocking[0].get("market_id"),
            "cooldown_type": "REJECTION_CLUSTER",
            "reason": "multiple_hard_engine_rejections",
            "started_at": now,
            "expires_at": now + timedelta(minutes=minutes),
            "active": True,
            "severity": "WARNING",
        }

