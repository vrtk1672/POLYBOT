from app.risk.correlation_checker import CorrelationChecker


def test_correlation_blocks_family_exposure():
    ok, reason = CorrelationChecker().check(market_family="sports", family_exposure={"sports": 240}, proposed_size_usd=20, max_family_exposure={"sports": 250})
    assert ok is False
    assert reason == "market_family_exposure_breach"

