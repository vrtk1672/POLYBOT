from __future__ import annotations

from app.neural_mesh.paper_intents import NoTradeLedgerRecord


def test_no_trade_ledger_contract_preserves_reasons() -> None:
    record = NoTradeLedgerRecord(
        no_trade_id="nt-1",
        eligibility_id="e-1",
        no_trade_reason="RISK_NOT_APPROVED",
        no_trade_category="RISK_BLOCKED",
        blockers=["risk_not_approved"],
        missing_requirements=["risk_not_approved"],
    )

    assert record.no_trade_category == "RISK_BLOCKED"
    assert record.blockers == ["RISK_NOT_APPROVED"]
    assert record.missing_requirements == ["RISK_NOT_APPROVED"]
