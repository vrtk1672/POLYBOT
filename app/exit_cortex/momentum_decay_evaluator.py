from __future__ import annotations

from app.exit_cortex.contracts import ExitTrigger


class MomentumDecayEvaluator:
    def evaluate(self, *, plan, current: dict) -> ExitTrigger:
        score = float(current.get("momentum_score") or 0.0)
        threshold = float((plan.momentum_decay_exit or {}).get("min_momentum", 0.2))
        triggered = score < threshold
        return ExitTrigger(trigger_type="MOMENTUM_DECAY", triggered=triggered, severity="WARNING", reason="momentum_decay" if triggered else "momentum_ok", threshold=threshold, current_price=current.get("current_price"), confidence=0.7 if triggered else 0.4, details={"momentum_score": score})

