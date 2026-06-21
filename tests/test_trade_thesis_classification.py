from __future__ import annotations

from decimal import Decimal

from app.services.trade_thesis_engine import build_trade_thesis


def _record() -> dict[str, object]:
    return {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-1",
        "market_id": "market-1",
        "condition_id": "condition-1",
        "side": "YES",
        "token_id": "token-1",
        "entry_price": Decimal("0.40"),
    }


def _supported_edge() -> dict[str, object]:
    return {
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "edge_thesis_id": "edge-1",
        "source_refresh_cycle_id": "cycle-1",
        "opposing_neurons": [],
    }


def test_valid_mispricing_reversion_uses_early_exit_thesis() -> None:
    thesis = build_trade_thesis(
        _record(),
        {
            "edge": _supported_edge(),
            "risk": {"evaluation_id": "risk-1"},
            "payout": {"evaluation_id": "payout-1", "risk_reward": Decimal("1.2"), "profit_if_win": Decimal("40")},
            "exit_hold": {"evaluation_id": "exit-1", "exit_now_price": Decimal("0.46"), "liquidity_exit_quality": "FAIR"},
            "orderbook": {"id": "book-1", "best_bid": Decimal("0.46"), "spread": Decimal("0.02")},
        },
    )

    assert thesis["status"] == "THESIS_SUPPORTED"
    assert thesis["trade_thesis_type"] == "MISPRICING_REVERSION"
    assert thesis["exit_intent"] == "PRICE_TARGET_EXIT"
    assert thesis["expected_hold_time_hours"] == Decimal("48")
    assert thesis["metadata_json"]["no_probability_fabricated"] is True


def test_long_market_without_supported_edge_does_not_get_early_exit_hold_time() -> None:
    thesis = build_trade_thesis(
        _record(),
        {
            "edge": {"edge_state": "EDGE_WATCH", "source_backed": False, "risk_usable": False},
            "payout": {"evaluation_id": "payout-1", "risk_reward": Decimal("1.2"), "profit_if_win": Decimal("40")},
            "exit_hold": {"evaluation_id": "exit-1", "time_to_resolution_seconds": 200 * 24 * 3600},
            "orderbook": {"id": "book-1", "best_bid": Decimal("0.46"), "spread": Decimal("0.02")},
        },
    )

    assert thesis["status"] == "THESIS_MISSING"
    assert thesis["expected_hold_time_hours"] is None
    assert thesis["blocker_code"] == "THESIS_REQUIRES_EDGE_SUPPORTED"


def test_orderbook_only_thesis_is_watch_not_supported() -> None:
    thesis = build_trade_thesis(
        _record(),
        {
            "edge": _supported_edge(),
            "risk": {"evaluation_id": "risk-1"},
            "exit_hold": {"evaluation_id": "exit-1", "exit_now_price": Decimal("0.43"), "liquidity_exit_quality": "FAIR"},
            "orderbook": {"id": "book-1", "best_bid": Decimal("0.43"), "spread": Decimal("0.02")},
            "market_movement": {"id": 123},
        },
    )

    assert thesis["status"] == "THESIS_WATCH"
    assert thesis["trade_thesis_type"] == "MOMENTUM_CONTINUATION"
    assert thesis["expected_hold_time_hours"] is None
    assert thesis["blocker_code"] == "DERIVED_SIGNALS_WATCH_ONLY"
