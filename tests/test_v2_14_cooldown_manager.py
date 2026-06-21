from app.risk.contracts import RiskBreach
from app.risk.cooldown_manager import CooldownManager


def test_engine_loss_triggers_cooldown_and_blocks_engine():
    breach = RiskBreach(breach_type="MAX_ENGINE_LOSS", severity="BLOCKING", engine="HUNT", blocked=True)
    cooldown = CooldownManager().from_breach(breach)
    assert cooldown.engine == "HUNT"
    blocked, reason = CooldownManager().active_blocks(engine="HUNT", market_family=None, cooldowns=[cooldown.model_dump()])
    assert blocked is True
    assert reason == "active_cooldown"

