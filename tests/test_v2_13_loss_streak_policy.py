from app.capital.loss_streak_policy import LossStreakPolicy


def test_loss_streak_reduces_aggressive_engines_fastest():
    policy = LossStreakPolicy()
    assert policy.multiplier(engine="SAFE", loss_streak_count=1) > policy.multiplier(engine="HUNT", loss_streak_count=1)
    assert policy.blocks(engine="CONVEX", loss_streak_count=3) is True
    assert policy.multiplier(engine="SAFE", loss_streak_count=3) > 0

