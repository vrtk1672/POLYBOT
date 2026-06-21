import pytest

from app.no_trade.no_trade_errors import NoTradeValidationError
from app.no_trade.service import NoTradeService
from test_v2_17_fixtures import no_trade_payload


def test_service_dry_run_writes_nothing():
    result = NoTradeService().log_decision(no_trade_payload(), dry_run=True)
    assert result["written"] is False
    assert result["decision"]["candidate_engine"] == "STRIKE"


def test_service_rejects_missing_reason():
    with pytest.raises(NoTradeValidationError):
        NoTradeService().log_decision(no_trade_payload(primary_reason=None, reasons=[]), dry_run=True)


def test_rebuild_dry_run_returns_candidates_without_writes():
    result = NoTradeService().rebuild(dry_run=True, source_layer="manual_smoke")
    assert result["written"] is False

