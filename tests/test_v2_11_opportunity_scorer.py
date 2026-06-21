from app.opportunity.contracts import OpportunityInput
from app.opportunity.opportunity_scorer import OpportunityScorer


def _strong_input(**overrides):
    base = {
        "market_id": "m1",
        "side": "YES",
        "context_output": {"strength": 0.9, "confidence": 0.9, "already_priced_in_score": 0.1, "urgency_score": 0.7},
        "capital_output": {"capital_allowed": True, "allocation_confidence": 0.9, "capital_recycling_score": 0.7},
        "technical_truth": {
            "technical_score": 0.8,
            "data_completeness_score": 1.0,
            "technical_blocked": False,
            "orderbook_signal": {"has_bid_ask": True, "spread_bps": 80, "depth_2c": 500},
            "liquidity_signal": {"entry_liquidity_score": 0.8, "exit_liquidity_score": 0.8, "exit_quality_score": 0.85, "expected_slippage_bps": 70, "max_safe_size_usd": 1000},
            "time_signal": {"time_efficiency_score": 0.7, "lockup_penalty_score": 0.1},
            "fee_reward_signal": {"reward_score": 0.2, "friction_score": 0.1, "net_edge_after_costs": 0.7},
        },
        "market_memory": {"memory_confidence": 0.8, "wording_risk_avg": 0.1, "whale_memory": {"whale_score": 0.8, "confidence": 0.8}},
        "whale_signals": [{"follow_value": 0.8}],
        "social_signals": [{"hype_pressure": 0.5, "bot_risk": 0.1, "spam_ratio": 0.1}],
        "fee_reward_signal": {"reward_score": 0.2, "friction_score": 0.1, "net_edge_after_costs": 0.7},
        "data_completeness_score": 1.0,
    }
    base.update(overrides)
    return OpportunityInput(**base)


def test_good_trigger_boosts_score_and_candidate_engines_are_suggestions():
    score, inputs = OpportunityScorer().score(_strong_input())

    assert score.opportunity_score > 0.3
    assert score.score_band in {"WATCHLIST", "STRONG", "HIGH_CONVICTION"}
    assert "STRIKE" in score.candidate_engines
    assert inputs


def test_missing_data_is_explicit_and_lowers_score():
    score, _ = OpportunityScorer().score(OpportunityInput(market_id="m1", insufficient_data_reasons=["missing_context_output"]))

    assert score.insufficient_data is True
    assert "missing_context_output" in score.insufficient_data_reasons
    assert score.opportunity_score < 0.2


def test_wording_risk_and_priced_in_reduce_score():
    base, _ = OpportunityScorer().score(_strong_input())
    risky, _ = OpportunityScorer().score(_strong_input(context_output={"strength": 0.9, "confidence": 0.9, "already_priced_in_score": 0.9}, market_memory={"memory_confidence": 0.8, "wording_risk_avg": 0.7}))

    assert risky.opportunity_score < base.opportunity_score
    assert "already_priced_in" in risky.no_trade_reasons
    assert any(flag.risk_flag == "high_wording_risk" for flag in risky.risk_flags)


def test_bad_liquidity_missing_bid_ask_and_poor_exit_block():
    score, _ = OpportunityScorer().score(_strong_input(technical_truth={"technical_score": 0.8, "technical_blocked": False, "orderbook_signal": {"has_bid_ask": False, "depth_2c": 0}, "liquidity_signal": {"exit_quality_score": 0.1, "max_safe_size_usd": 0}}))

    assert score.score_band == "BLOCKED"
    assert "missing_bid_ask" in score.no_trade_reasons
    assert "poor_exit_quality" in score.no_trade_reasons


def test_reward_pool_cannot_override_bad_liquidity():
    score, _ = OpportunityScorer().score(_strong_input(fee_reward_signal={"reward_score": 1.0}, technical_truth={"technical_score": 0.8, "orderbook_signal": {"has_bid_ask": False, "depth_2c": 0}, "liquidity_signal": {"exit_quality_score": 0.0, "max_safe_size_usd": 0}}))

    assert score.score_band == "BLOCKED"


def test_reproducibility_hash_is_stable_for_same_inputs():
    scorer = OpportunityScorer()
    one, _ = scorer.score(_strong_input())
    two, _ = scorer.score(_strong_input())

    assert one.reproducibility_hash == two.reproducibility_hash

