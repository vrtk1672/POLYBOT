from app.risk.contracts import RiskGovernorState
from app.risk.risk_breach_detector import RiskBreachDetector


def test_engine_loss_or_daily_loss_creates_blocking_breach():
    state = RiskGovernorState(daily_loss_usd=100, max_daily_loss_usd=50)
    breaches = RiskBreachDetector().detect_governor_breaches(state)
    assert breaches
    assert breaches[0].blocked is True

