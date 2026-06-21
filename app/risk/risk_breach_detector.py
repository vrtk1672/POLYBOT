from __future__ import annotations

from app.risk.contracts import RiskBreach, RiskGovernorState


class RiskBreachDetector:
    def detect_governor_breaches(self, state: RiskGovernorState) -> list[RiskBreach]:
        breaches: list[RiskBreach] = []
        if state.daily_loss_usd >= state.max_daily_loss_usd:
            breaches.append(RiskBreach(breach_type="MAX_DAILY_LOSS", severity="BLOCKING", observed_value=state.daily_loss_usd, limit_value=state.max_daily_loss_usd, blocked=True, explanation="daily loss limit reached"))
        if state.weekly_loss_usd >= state.max_weekly_loss_usd:
            breaches.append(RiskBreach(breach_type="MAX_WEEKLY_LOSS", severity="BLOCKING", observed_value=state.weekly_loss_usd, limit_value=state.max_weekly_loss_usd, blocked=True, explanation="weekly loss limit reached"))
        if state.open_positions_count >= state.max_open_positions:
            breaches.append(RiskBreach(breach_type="MAX_OPEN_POSITIONS", severity="BLOCKING", observed_value=state.open_positions_count, limit_value=state.max_open_positions, blocked=True, explanation="open position count limit reached"))
        if state.open_exposure_usd >= state.max_total_exposure_usd:
            breaches.append(RiskBreach(breach_type="MAX_TOTAL_EXPOSURE", severity="BLOCKING", observed_value=state.open_exposure_usd, limit_value=state.max_total_exposure_usd, blocked=True, explanation="total exposure limit reached"))
        return breaches

