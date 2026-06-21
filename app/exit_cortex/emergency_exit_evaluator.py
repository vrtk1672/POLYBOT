from __future__ import annotations

from app.exit_cortex.contracts import ExitTrigger


class EmergencyExitEvaluator:
    def evaluate(self, *, plan, current: dict) -> ExitTrigger:
        gov = str(current.get("governor_status") or "OK").upper()
        adverse = float(current.get("adverse_move_pct") or 0.0)
        threshold = float((plan.emergency_exit or {}).get("adverse_move_pct", 0.25))
        triggered = gov in {"KILL", "BLOCKED", "COOLDOWN"} or adverse >= threshold or bool(current.get("emergency"))
        return ExitTrigger(trigger_type="EMERGENCY_EXIT", triggered=triggered, severity="BLOCKING" if triggered else "INFO", reason="emergency_exit_triggered" if triggered else "no_emergency", threshold=threshold, confidence=1.0 if triggered else 0.5, details={"governor_status": gov, "adverse_move_pct": adverse})

