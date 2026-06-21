from __future__ import annotations

from app.services.paper_defense import defense_profile


def test_threshold_scaling_by_defense_level() -> None:
    assert str(defense_profile(100).adjusted_threshold) == "60"
    assert str(defense_profile(80).adjusted_threshold) == "57"
    assert str(defense_profile(60).adjusted_threshold) == "53"
    assert str(defense_profile(40).adjusted_threshold) == "48"
    assert str(defense_profile(20).adjusted_threshold) == "42"
    assert str(defense_profile(0).adjusted_threshold) == "30"
