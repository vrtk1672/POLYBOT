from __future__ import annotations

from app.exit_cortex.contracts import ExitTrigger


class SpreadExitEvaluator:
    def evaluate(self, *, plan, current: dict) -> ExitTrigger:
        spread = float(current.get("spread_bps") or 0.0)
        threshold = float((plan.spread_exit or {}).get("max_spread_bps", 500))
        triggered = spread > threshold
        return ExitTrigger(trigger_type="SPREAD_EXIT", triggered=triggered, severity="WARNING", reason="spread_exit" if triggered else "spread_ok", threshold=threshold, confidence=0.8 if triggered else 0.4, details={"spread_bps": spread})

