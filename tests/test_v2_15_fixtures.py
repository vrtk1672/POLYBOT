from __future__ import annotations


def approved_payload(*, runtime_mode: str = "PAPER", depth: float = 120.0, slippage: float = 20.0) -> dict:
    return {
        "runtime_mode": runtime_mode,
        "strategy_route": {
            "id": 1,
            "market_id": "m1",
            "side": "YES",
            "selected_engine": "SAFE",
            "route_status": "ROUTED",
            "entry_price_max": 0.55,
            "max_hold_minutes": 5,
            "engine_contract_json": {"entry_price_max": 0.55, "expected_hold_minutes": 5},
        },
        "capital_allocation": {
            "allocation_id": "alloc_1",
            "market_id": "m1",
            "side": "YES",
            "engine": "SAFE",
            "allocation_status": "ALLOCATED",
            "approved_size_usd": 20.0,
            "requested_size_usd": 20.0,
        },
        "risk_decision": {
            "id": 1,
            "run_id": "risk_run_1",
            "market_id": "m1",
            "side": "YES",
            "engine": "SAFE",
            "decision": "APPROVED",
            "approved": True,
            "approved_position_size_usd": 20.0,
            "constraints_json": {"max_slippage_bps": 150.0},
        },
        "governor_state": {"governor_status": "OK"},
        "orderbook": {
            "token_id": "token_yes",
            "best_bid": 0.49,
            "best_ask": 0.51,
            "mid_price": 0.50,
            "spread_bps": slippage,
            "depth_2c": depth,
            "depth_5c": depth,
            "has_bid_ask": True,
        },
        "liquidity": {"expected_slippage_bps": slippage, "exit_quality_score": 0.8},
        "fee": {"taker_cost_bps": 5.0},
    }

