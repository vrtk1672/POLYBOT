from __future__ import annotations


AGGRESSIVE_ENGINES = {"HUNT", "CONVEX", "MOONSHOT_BASKET"}


class LossStreakPolicy:
    def multiplier(self, *, engine: str, loss_streak_count: int) -> float:
        engine = str(engine or "").upper()
        losses = max(int(loss_streak_count or 0), 0)
        if losses <= 0:
            return 1.0
        if losses == 1:
            return 0.75 if engine in AGGRESSIVE_ENGINES else 0.85
        if losses == 2:
            return 0.35 if engine in AGGRESSIVE_ENGINES else 0.60
        if engine in AGGRESSIVE_ENGINES:
            return 0.0
        if engine == "SAFE":
            return 0.40
        return 0.25

    def blocks(self, *, engine: str, loss_streak_count: int) -> bool:
        return self.multiplier(engine=engine, loss_streak_count=loss_streak_count) <= 0

