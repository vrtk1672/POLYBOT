from __future__ import annotations


class CorrelationChecker:
    def check(self, *, market_family: str | None, family_exposure: dict[str, float], proposed_size_usd: float, max_family_exposure: dict[str, float]) -> tuple[bool, str | None]:
        if not market_family:
            return True, None
        current = float(family_exposure.get(market_family, 0.0) or 0.0)
        limit = float(max_family_exposure.get(market_family, max_family_exposure.get("*", 250.0)) or 250.0)
        if current + max(proposed_size_usd, 0.0) > limit:
            return False, "market_family_exposure_breach"
        return True, None

