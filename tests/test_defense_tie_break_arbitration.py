from __future__ import annotations

from app.services.same_market_arbitration import SameMarketSideArbitrator


def test_defense_20_can_use_deterministic_learning_tie_break() -> None:
    result = SameMarketSideArbitrator(defense_level=20).arbitrate([_decision("YES"), _decision("NO")])
    enters = [item for item in result if item["decision"] == "ENTER"]

    assert len(enters) == 1
    assert enters[0]["policy_json"]["same_market_side_arbitration"]["outcome"] == "TIE_BROKEN_FOR_LEARNING"
    assert enters[0]["policy_json"]["same_market_side_arbitration"]["tie_breaker_used"] == "deterministic_hash_market_session"


def test_defense_0_chooses_technically_executable_side_on_exact_tie() -> None:
    result = SameMarketSideArbitrator(defense_level=0).arbitrate([_decision("YES"), _decision("NO")])

    assert len([item for item in result if item["decision"] == "ENTER"]) == 1


def _decision(side: str) -> dict:
    return {
        "decision_id": f"decision-tie-break-{side}",
        "market_id": "market-tie-break",
        "side": side,
        "token_id": f"token-{side}",
        "decision": "ENTER",
        "paper_enter_allowed": True,
        "opportunity_score": 55.46,
        "edge_state": "EDGE_SUPPORTED",
        "thesis_state": "THESIS_SUPPORTED",
        "exit_state": "EXIT_READY",
        "orderbook_state": "FRESH",
        "blockers_json": [],
        "warnings_json": [],
        "required_to_pass_json": [],
        "policy_json": {},
        "evidence": {
            "side_evidence": {"direction_for_market": "UNKNOWN", "direction_confidence": 0},
            "orderbook_best_bid": 0.40,
            "orderbook_best_ask": 0.42,
            "orderbook_liquidity_score": 0.80,
            "orderbook_age_seconds": 5,
            "orderbook_ttl_seconds": 60,
        },
    }
