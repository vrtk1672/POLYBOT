from __future__ import annotations

from typing import Any


class NewsTTLEngine:
    def compute_ttl_seconds(
        self,
        news_event: dict[str, Any],
        impact_score: dict[str, Any] | Any,
        market: dict[str, Any] | None = None,
    ) -> int:
        category = str(news_event.get("category") or (market or {}).get("category") or "").lower()
        urgency = float(news_event.get("urgency_score") or getattr(impact_score, "urgency", 0.5) or 0.5)
        confidence = float(getattr(impact_score, "confidence", 0.5) if not isinstance(impact_score, dict) else impact_score.get("confidence", 0.5))
        priced_in = float(getattr(impact_score, "already_priced_in", 0.0) if not isinstance(impact_score, dict) else impact_score.get("already_priced_in", 0.0))
        if category in {"sports", "crypto"}:
            ttl = 900
        elif category in {"legal", "politics", "geopolitics"}:
            ttl = 21600
        else:
            ttl = 3600
        if urgency >= 0.75:
            ttl = min(ttl, 1200)
        ttl = int(ttl * max(0.2, confidence) * max(0.1, 1.0 - priced_in))
        return max(0, ttl)

