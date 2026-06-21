from __future__ import annotations

from app.services.same_market_arbitration import SameMarketSideArbitrator


def test_higher_arbitration_score_side_is_selected() -> None:
    result = SameMarketSideArbitrator(defense_level=20).arbitrate(
        [_decision("market-side-arb", "YES", 63.0), _decision("market-side-arb", "NO", 55.0)]
    )
    yes = next(item for item in result if item["side"] == "YES")
    no = next(item for item in result if item["side"] == "NO")

    assert yes["decision"] == "ENTER"
    assert no["decision"] == "BLOCK"
    assert "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION" in no["blockers_json"]
    assert yes["evidence"]["same_market_side_arbitration"]["selected_side"] == "YES"


def test_both_sides_are_not_opened_as_normal_trades() -> None:
    result = SameMarketSideArbitrator(defense_level=20).arbitrate(
        [_decision("market-one-side", "YES", 61.0), _decision("market-one-side", "NO", 59.0)]
    )

    assert len([item for item in result if item["decision"] == "ENTER"]) == 1


def _decision(market_id: str, side: str, score: float) -> dict:
    return {
        "decision_id": f"decision-{market_id}-{side}",
        "market_id": market_id,
        "side": side,
        "token_id": f"token-{market_id}-{side}",
        "decision": "ENTER",
        "paper_enter_allowed": True,
        "opportunity_score": score,
        "edge_state": "EDGE_SUPPORTED",
        "thesis_state": "THESIS_SUPPORTED",
        "exit_state": "EXIT_READY",
        "orderbook_state": "FRESH",
        "blockers_json": [],
        "warnings_json": [],
        "required_to_pass_json": [],
        "policy_json": {},
        "evidence": {"orderbook_age_seconds": 5, "orderbook_ttl_seconds": 60},
    }
