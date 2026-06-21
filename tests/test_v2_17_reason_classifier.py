from app.no_trade.reason_classifier import NoTradeReasonClassifier


def test_common_reasons_classify():
    c = NoTradeReasonClassifier()
    assert c.classify("low_edge").reason == "low_edge"
    assert c.classify("low_liquidity").reason == "low_liquidity"
    assert c.classify("wide_spread").reason == "wide_spread"
    assert c.classify("bad_rules").reason == "bad_rules"
    assert c.classify("high_wording_risk").reason == "high_wording_risk"
    assert c.classify("high_correlation").reason == "high_correlation"
    assert c.classify("no_capital").reason == "no_capital"
    assert c.classify("bad_exit_quality").reason == "bad_exit_quality"
    assert c.classify("already_priced_in").reason == "already_priced_in"
    assert c.classify("high_slippage").reason == "high_slippage"
    assert c.classify("governor_block").reason == "governor_block"
    assert c.classify("ai_uncertainty").reason == "ai_uncertainty"


def test_unknown_reason_becomes_unknown_and_insufficient():
    reason = NoTradeReasonClassifier().classify("mysterious thing", source_layer="strategy")
    assert reason.reason == "unknown_reason"
    assert reason.severity == "WARNING"

