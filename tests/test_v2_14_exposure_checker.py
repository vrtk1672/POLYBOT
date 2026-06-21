from app.risk.exposure_checker import ExposureChecker


def test_exposure_and_open_positions_block():
    checker = ExposureChecker()
    assert checker.check(open_exposure_usd=490, proposed_size_usd=20, max_total_exposure_usd=500)[0] is False
    assert checker.check_open_positions(open_positions_count=5, max_open_positions=5)[0] is False

