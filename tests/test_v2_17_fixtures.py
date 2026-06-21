from __future__ import annotations


def no_trade_payload(**overrides):
    payload = {
        "market_id": "2169995",
        "market_family": "politics",
        "side": "YES",
        "candidate_engine": "STRIKE",
        "source_layer": "manual_smoke",
        "source_run_id": "run_1",
        "source_record_id": "record_1",
        "decision_status": "BLOCKED",
        "primary_reason": "low_liquidity",
        "reasons": ["low_liquidity", "wide_spread"],
        "opportunity_score": 0.42,
        "would_have_entry_price": 0.5,
        "would_have_size_usd": 20.0,
        "decision_confidence": 0.8,
        "data_confidence": 0.8,
        "explanation": "Smoke no-trade because liquidity was poor.",
    }
    payload.update(overrides)
    return payload


def favorable_evidence(**overrides):
    payload = {
        "observed_price_at_decision": 0.5,
        "observed_price_after": 0.75,
        "observed_max_favorable_move": 0.78,
        "observed_max_adverse_move": 0.48,
        "would_have_exit_possible": True,
        "liquidity_after_score": 0.8,
    }
    payload.update(overrides)
    return payload

