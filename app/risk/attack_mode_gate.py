from __future__ import annotations

from app.risk.contracts import RiskGovernorState


class AttackModeGate:
    def evaluate(self, *, state: RiskGovernorState, attack_bank_available: float, approval: bool) -> tuple[bool, str | None]:
        if not approval:
            return False, "missing_governor_attack_approval"
        if state.governor_status != "OK":
            return False, "governor_not_clean"
        if state.active_breaches:
            return False, "active_breaches"
        if state.daily_loss_usd > 0 or state.weekly_loss_usd > 0:
            return False, "loss_breach_or_drawdown_present"
        if attack_bank_available <= 0:
            return False, "attack_bank_unavailable"
        return True, None

