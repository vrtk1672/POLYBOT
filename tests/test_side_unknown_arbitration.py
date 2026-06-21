from __future__ import annotations

from app.services.same_market_arbitration import SameMarketSideArbitrator


def test_defense_100_keeps_side_unknown_exact_tie_unresolved() -> None:
    result = SameMarketSideArbitrator(defense_level=100).arbitrate([_decision("YES"), _decision("NO")])

    assert all(item["decision"] == "BLOCK" for item in result)
    assert all("SAME_MARKET_OPPOSING_SIDE_UNRESOLVED" in item["blockers_json"] for item in result)


def test_side_unknown_is_recorded_in_arbitration_evidence() -> None:
    result = SameMarketSideArbitrator(defense_level=100).arbitrate([_decision("YES"), _decision("NO")])
    yes = next(item for item in result if item["side"] == "YES")

    arbitration = yes["policy_json"]["same_market_side_arbitration"]
    assert arbitration["side_unknown_count"] == 2
    assert any("explicit event/source direction" in item for item in arbitration["missing_side_evidence_json"])


def _decision(side: str) -> dict:
    return {
        "decision_id": f"decision-side-unknown-{side}",
        "market_id": "market-side-unknown",
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
