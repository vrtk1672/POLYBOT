from app.risk.risk_limit_manager import RiskLimitManager


def test_default_conservative_limits_created():
    limits = RiskLimitManager().as_dict()
    assert limits["MAX_DAILY_LOSS"] <= 50
    assert limits["EXIT_PLAN_REQUIRED"] is True
    assert limits["MIN_CONFIDENCE"] >= 0.5

