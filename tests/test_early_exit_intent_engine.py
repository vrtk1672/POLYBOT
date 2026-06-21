from __future__ import annotations

from decimal import Decimal

from app.services.trade_thesis_engine import build_trade_thesis


def test_missing_exit_intent_support_keeps_early_exit_on_watch() -> None:
    thesis = build_trade_thesis(
        {
            "subject_type": "PAPER_CANDIDATE",
            "subject_id": "candidate-1",
            "market_id": "market-1",
            "side": "YES",
            "token_id": "token-1",
            "entry_price": Decimal("0.40"),
        },
        {
            "edge": {"edge_state": "EDGE_SUPPORTED", "source_backed": True, "risk_usable": True, "edge_thesis_id": "edge-1"},
            "risk": {"evaluation_id": "risk-1"},
            "payout": {"evaluation_id": "payout-1", "risk_reward": Decimal("1.4"), "profit_if_win": Decimal("60")},
            "exit_hold": {"evaluation_id": "exit-1", "liquidity_exit_quality": "EXIT_LIQUIDITY_UNKNOWN"},
            "orderbook": {"id": "book-1"},
        },
    )

    assert thesis["trade_thesis_type"] == "MISPRICING_REVERSION"
    assert thesis["status"] == "THESIS_WATCH"
    assert thesis["expected_hold_time_hours"] is None
    assert thesis["blocker_code"] == "EXIT_INTENT_NOT_CURRENTLY_SUPPORTED"


def test_ai_fallback_does_not_invent_sources_or_probabilities() -> None:
    thesis = build_trade_thesis(
        {
            "subject_type": "PAPER_CANDIDATE",
            "subject_id": "candidate-1",
            "market_id": "market-1",
            "side": "YES",
            "token_id": "token-1",
            "entry_price": Decimal("0.40"),
        },
        {
            "edge": {"edge_state": "EDGE_SUPPORTED", "source_backed": True, "risk_usable": True, "edge_thesis_id": "edge-1"},
            "risk": {"evaluation_id": "risk-1"},
            "payout": {"evaluation_id": "payout-1", "risk_reward": Decimal("1.4"), "profit_if_win": Decimal("60")},
            "exit_hold": {"evaluation_id": "exit-1", "exit_now_price": Decimal("0.46"), "liquidity_exit_quality": "FAIR"},
            "orderbook": {"id": "book-1", "best_bid": Decimal("0.46"), "spread": Decimal("0.02")},
        },
    )

    assert thesis["ai_review_state"] == "UNAVAILABLE"
    assert thesis["metadata_json"]["no_ai_sources_added"] is True
    assert thesis["metadata_json"]["no_probability_fabricated"] is True
