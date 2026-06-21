from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.repositories.market_family_repository import MarketFamilyRepository


class MarketFamilyClassifier:
    classifier_version = "v2.2_rule_based"

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: MarketFamilyRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or MarketFamilyRepository()

    def classify(self, raw_market: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(
            str(raw_market.get(key) or "")
            for key in ("question", "slug", "category", "event_title", "eventTitle")
        ).lower()
        tags = _as_list(raw_market.get("tags") or raw_market.get("tagsJson"))
        tag_text = " ".join(str(tag).lower() for tag in tags)
        combined = f"{text} {tag_text}"
        category = raw_market.get("category")
        family = "generic"
        subcategory = None
        confidence = 0.35
        reason = "generic fallback"
        if any(word in combined for word in ("bitcoin", "btc", "ethereum", "eth", "crypto")):
            family = "crypto-short-window" if any(word in combined for word in ("5m", "15m", "hour", "daily")) else "crypto-long-horizon"
            category = category or "crypto"
            confidence = 0.82
            reason = "crypto terms found"
        elif any(word in combined for word in ("election", "president", "senate", "mayor", "vote")):
            family = "politics-election"
            category = category or "politics"
            confidence = 0.82
            reason = "election terms found"
        elif any(word in combined for word in ("nba", "nfl", "soccer", "premier league", "win the game", "vs ")):
            family = "sports-pre-match"
            category = category or "sports"
            confidence = 0.76
            reason = "sports terms found"
        elif any(word in combined for word in ("fed", "inflation", "cpi", "gdp", "interest rate")):
            family = "macro-economic"
            category = category or "macro"
            confidence = 0.74
            reason = "macro terms found"
        elif any(word in combined for word in ("hurricane", "weather", "temperature", "rain")):
            family = "weather-event"
            category = category or "weather"
            confidence = 0.72
            reason = "weather terms found"
        elif any(word in combined for word in ("court", "supreme court", "lawsuit")):
            family = "legal-court"
            category = category or "legal"
            confidence = 0.72
            reason = "legal terms found"
        elif any(word in combined for word in ("war", "iran", "russia", "ukraine", "gaza", "china")):
            family = "geopolitics"
            category = category or "geopolitics"
            confidence = 0.7
            reason = "geopolitical terms found"
        elif any(word in combined for word in ("eurovision", "oscars", "grammy", "movie")):
            family = "entertainment"
            category = category or "entertainment"
            confidence = 0.68
            reason = "entertainment terms found"
        return {
            "market_family": family,
            "category": category,
            "subcategory": subcategory,
            "tags": tags,
            "confidence": confidence,
            "reason": reason,
            "classifier_version": self.classifier_version,
        }

    def persist(self, market_id: str, classification: dict[str, Any]) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            return self._repository.upsert_family(
                conn,
                market_id=market_id,
                market_family=classification["market_family"],
                category=classification.get("category"),
                subcategory=classification.get("subcategory"),
                tags=classification.get("tags") or [],
                confidence=float(classification.get("confidence") or 0),
                reason=classification.get("reason"),
                metadata={"classifier_version": self.classifier_version},
            )


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        import json

        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, list) else [value]
        except json.JSONDecodeError:
            return [value] if value else []
    return []
