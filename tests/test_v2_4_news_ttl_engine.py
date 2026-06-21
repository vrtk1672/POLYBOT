from __future__ import annotations

from app.news_neuron.ttl_engine import NewsTTLEngine


def test_ttl_heuristics_are_non_negative_and_contextual() -> None:
    ttl = NewsTTLEngine()
    sports = ttl.compute_ttl_seconds({"category": "sports", "urgency_score": 0.9}, {"confidence": 0.8, "already_priced_in": 0.1})
    legal = ttl.compute_ttl_seconds({"category": "legal", "urgency_score": 0.2}, {"confidence": 0.8, "already_priced_in": 0.1})
    priced = ttl.compute_ttl_seconds({"category": "legal", "urgency_score": 0.2}, {"confidence": 0.8, "already_priced_in": 0.9})
    assert sports < legal
    assert priced < legal
    assert sports >= 0

