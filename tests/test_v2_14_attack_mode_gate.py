from app.risk.attack_mode_gate import AttackModeGate
from app.risk.contracts import RiskGovernorState


def test_attack_mode_blocked_without_governor_approval():
    allowed, reason = AttackModeGate().evaluate(state=RiskGovernorState(governor_status="OK"), attack_bank_available=100, approval=False)
    assert allowed is False
    assert reason == "missing_governor_attack_approval"


def test_attack_mode_allowed_only_clean_with_attack_bank_and_approval():
    allowed, reason = AttackModeGate().evaluate(state=RiskGovernorState(governor_status="OK"), attack_bank_available=100, approval=True)
    assert allowed is True
    assert reason is None

