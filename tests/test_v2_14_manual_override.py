import pytest

from app.risk.manual_override_auditor import ManualOverrideAuditor
from app.risk.risk_errors import ManualOverrideRejected


def test_manual_override_requires_audit_fields():
    with pytest.raises(ManualOverrideRejected):
        ManualOverrideAuditor().validate({"actor": "op"})


def test_manual_override_cannot_bypass_kill():
    with pytest.raises(ManualOverrideRejected):
        ManualOverrideAuditor().validate({"actor": "op", "reason": "no", "scope": "ENGINE", "override_type": "BYPASS_KILL"}, governor_status="KILL")


def test_manual_override_is_audited():
    row = ManualOverrideAuditor().validate({"actor": "op", "reason": "test", "scope": "ENGINE", "override_type": "SOFT_RISK"})
    assert row["override_id"].startswith("risk_override_")
    assert row["reason"] == "test"

