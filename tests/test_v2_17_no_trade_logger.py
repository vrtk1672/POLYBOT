from app.no_trade.no_trade_logger import NoTradeLogger
from test_v2_17_fixtures import no_trade_payload


def test_blocked_candidate_logs_no_trade_decision():
    decision = NoTradeLogger().build(no_trade_payload())
    assert decision.decision_status == "BLOCKED"
    assert decision.reasons

