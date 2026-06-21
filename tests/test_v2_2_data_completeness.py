from __future__ import annotations

from app.data_foundation.data_completeness import DataCompletenessComputer


def _market(**overrides):
    base = {
        "market_id": "m1",
        "question": "Will data be complete?",
        "yes_token_id": "yes",
        "no_token_id": "no",
        "accepting_orders": True,
        "closed": False,
        "close_time": "future",
        "resolution_source": "official",
    }
    base.update(overrides)
    return base


def test_complete_market_candidate_allowed() -> None:
    result = DataCompletenessComputer().compute_data_completeness(
        market=_market(),
        rules={"rules_text": "Resolve yes if true", "resolution_source": "official"},
        latest_snapshot={"current_price_yes": 0.5, "time_to_close_seconds": 3600},
        orderbook={"best_bid": 0.49, "best_ask": 0.51, "depth_2c": 100},
        liquidity={"liquidity_score": 75},
    )
    assert result.candidate_allowed is True
    assert result.score == 100


def test_missing_orderbook_lowers_score() -> None:
    result = DataCompletenessComputer().compute_data_completeness(
        market=_market(),
        rules={"rules_text": "x"},
        latest_snapshot={"current_price_yes": 0.5, "time_to_close_seconds": 3600},
        orderbook=None,
        liquidity={"liquidity_score": 75},
    )
    assert "orderbook" in result.missing_fields
    assert result.candidate_allowed is False


def test_missing_rules_lowers_score() -> None:
    result = DataCompletenessComputer().compute_data_completeness(
        market=_market(),
        latest_snapshot={"current_price_yes": 0.5, "time_to_close_seconds": 3600},
        orderbook={"best_bid": 0.49},
        liquidity={"liquidity_score": 75},
    )
    assert "rules" in result.missing_fields


def test_closed_or_stale_market_blocked() -> None:
    closed = DataCompletenessComputer().compute_data_completeness(
        market=_market(closed=True),
        rules={"rules_text": "x"},
        latest_snapshot={"current_price_yes": 0.5, "time_to_close_seconds": 3600},
        orderbook={"best_bid": 0.49},
        liquidity={"liquidity_score": 75},
    )
    stale = DataCompletenessComputer().compute_data_completeness(
        market=_market(),
        rules={"rules_text": "x"},
        latest_snapshot={"current_price_yes": 0.5, "time_to_close_seconds": 3600},
        orderbook={"best_bid": 0.49},
        liquidity={"liquidity_score": 75},
        stale_fields=["market_snapshot"],
    )
    assert closed.candidate_allowed is False
    assert stale.candidate_allowed is False


def test_missing_token_mapping_candidate_blocked() -> None:
    result = DataCompletenessComputer().compute_data_completeness(
        market=_market(yes_token_id=None, no_token_id=None),
        rules={"rules_text": "x"},
        latest_snapshot={"current_price_yes": 0.5, "time_to_close_seconds": 3600},
        orderbook={"best_bid": 0.49},
        liquidity={"liquidity_score": 75},
    )
    assert result.candidate_allowed is False
