import pytest

from app.no_trade.candidate_tracker import NoTradeCandidateTracker
from app.no_trade.no_trade_errors import NoTradeValidationError
from test_v2_17_fixtures import no_trade_payload


def test_candidate_engine_and_source_layer_are_stored():
    decision = NoTradeCandidateTracker().build_decision(no_trade_payload())
    assert decision.candidate_engine == "STRIKE"
    assert decision.source_layer == "manual_smoke"
    assert decision.primary_reason == "low_liquidity"


def test_reason_required():
    with pytest.raises(NoTradeValidationError):
        NoTradeCandidateTracker().build_decision(no_trade_payload(primary_reason=None, reasons=[]))


def test_source_layer_required():
    with pytest.raises(NoTradeValidationError):
        NoTradeCandidateTracker().build_decision(no_trade_payload(source_layer=""))

