from __future__ import annotations

from datetime import UTC, datetime, timedelta


def completed_trade_payload(**overrides):
    now = datetime.now(UTC)
    payload = {
        "market_id": "2169995",
        "market_family": "politics",
        "side": "YES",
        "engine": "STRIKE",
        "order_id": "ord_v2_learning_1",
        "exit_plan_id": "exit_plan_learning_1",
        "entry_price": 0.42,
        "exit_price": 0.57,
        "size_usd": 100.0,
        "entry_time": (now - timedelta(minutes=30)).isoformat(),
        "exit_time": now.isoformat(),
        "completed": True,
        "predicted_slippage_bps": 30,
        "actual_slippage_bps": 35,
        "entry_quality_score": 0.84,
        "exit_quality_score": 0.79,
        "signals": [
            {
                "source_type": "technical",
                "signal_type": "momentum",
                "direction": "UP",
                "predicted_strength": 0.18,
                "observed_move": 0.15,
                "confidence": 0.82,
            }
        ],
        "sources": [
            {
                "source_type": "news",
                "source_name": "wire",
                "usefulness_score": 0.8,
                "prior_reliability": 0.6,
                "confidence": 0.8,
            }
        ],
        "whales": [
            {
                "whale_id": "wallet_abc",
                "hit": True,
                "prior_follow_value": 0.5,
                "prior_noise_score": 0.3,
                "confidence": 0.78,
            }
        ],
        "ai": [
            {
                "ai_request_id": "ai_req_1",
                "model_name": "local-review",
                "task_type": "market_review",
                "useful": True,
                "accuracy_score": 0.75,
                "cost_usd": 0.01,
                "confidence": 0.8,
            }
        ],
    }
    payload.update(overrides)
    return payload


def incomplete_trade_payload():
    return completed_trade_payload(exit_price=None, completed=False)
