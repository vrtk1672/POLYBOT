from __future__ import annotations

import os

import pytest

from app.db.connection import DatabaseConnectionFactory


def exit_plan_manual(**overrides) -> dict:
    payload = {
        "exit_plan_id": "exit_plan_test",
        "market_id": "m1",
        "order_id": "order_1",
        "entry_price": 0.50,
        "entry_size": 10.0,
        "target_exit": 0.72,
        "partial_take_profit": 0.64,
        "partial_take_profit_pct": 0.5,
        "stop_loss": 0.38,
        "max_hold_seconds": 300,
        "side": "YES",
        "engine": "SAFE",
        "exit_mode": "PAPER_SIM_EXIT",
        "liquidity_exit_check": {"require_bid_ask": True, "require_depth": True, "max_slippage_bps": 250, "min_exit_quality": 0.25},
        "invalidation_rule": {"enabled": True},
        "emergency_exit": {"enabled": True, "adverse_move_pct": 0.2},
        "spread_exit": {"max_spread_bps": 500},
        "momentum_decay_exit": {"min_momentum": 0.2},
        "news_invalidated_exit": {"enabled": True},
    }
    payload.update(overrides)
    return payload


def current_market(**overrides) -> dict:
    payload = {
        "runtime_mode": "PAPER",
        "current_price": 0.50,
        "position_age_seconds": 60,
        "best_bid": 0.49,
        "best_ask": 0.51,
        "depth_2c": 100.0,
        "expected_slippage_bps": 50.0,
        "exit_quality_score": 0.8,
        "spread_bps": 80.0,
        "momentum_score": 0.7,
        "governor_status": "OK",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def db_factory():
    if not os.getenv("POLYBOT_DATABASE_URL"):
        pytest.skip("POLYBOT_DATABASE_URL not configured")
    return DatabaseConnectionFactory()

