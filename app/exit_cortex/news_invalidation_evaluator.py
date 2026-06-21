from __future__ import annotations

from app.exit_cortex.contracts import ExitTrigger


class NewsInvalidationEvaluator:
    def evaluate(self, *, plan, current: dict) -> ExitTrigger:
        invalidated = bool(current.get("news_invalidated") or current.get("context_invalidated"))
        return ExitTrigger(trigger_type="NEWS_INVALIDATED", triggered=invalidated, severity="BLOCKING" if invalidated else "INFO", reason="news_invalidated" if invalidated else "news_not_invalidated", confidence=0.85 if invalidated else 0.4, details={"evidence": current.get("news_evidence")})

