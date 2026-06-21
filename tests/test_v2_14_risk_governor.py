from app.risk.risk_governor import RiskGovernor


def test_governor_kill_blocks_all():
    state = RiskGovernor().rebuild(runtime_mode="KILL", payload={"kill_switch_active": True})
    assert state.governor_status == "KILL"


def test_daily_and_weekly_loss_block():
    daily = RiskGovernor().rebuild(payload={"daily_loss_usd": 60})
    weekly = RiskGovernor().rebuild(payload={"weekly_loss_usd": 200})
    assert daily.governor_status == "BLOCKED"
    assert weekly.governor_status == "BLOCKED"


def test_engine_loss_breach_visible_for_cooldown():
    state = RiskGovernor().rebuild(payload={"engine_losses": {"HUNT": 30}, "max_engine_loss": {"HUNT": 25}})
    assert state.active_breaches
    assert state.active_breaches[0]["breach_type"] == "MAX_ENGINE_LOSS"
