from __future__ import annotations

from app.services.paper_defense import defense_profile


def test_capital_scaling_allows_around_80_percent_at_low_defense() -> None:
    strict = defense_profile(100)
    low = defense_profile(20)
    zero = defense_profile(0)

    assert str(strict.max_deployed_pct) == "20"
    assert str(low.max_deployed_pct) == "80"
    assert str(zero.max_deployed_pct) == "95"
    assert low.max_open_positions > strict.max_open_positions
    assert zero.max_single_trade_pct > strict.max_single_trade_pct
