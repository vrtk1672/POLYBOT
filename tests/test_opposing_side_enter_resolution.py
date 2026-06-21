from __future__ import annotations

from app.services.same_market_arbitration import SameMarketSideArbitrator


def test_opposing_side_resolution_keeps_only_clear_winner_enterable() -> None:
    decisions = [
        _decision("market-resolution", "YES", 64.0),
        _decision("market-resolution", "NO", 61.0),
    ]

    result = SameMarketSideArbitrator(defense_level=20).arbitrate(decisions)
    yes = next(item for item in result if item["side"] == "YES")
    no = next(item for item in result if item["side"] == "NO")

    assert yes["decision"] == "ENTER"
    assert yes["paper_enter_allowed"] is True
    assert "SAME_MARKET_OPPOSING_SIDE_ARBITRATION_WINNER" in yes["warnings_json"]
    assert no["decision"] == "BLOCK"
    assert no["paper_enter_allowed"] is False
    assert "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION" in no["blockers_json"]


def _decision(market_id: str, side: str, score: float) -> dict:
    return {
        "decision_id": f"decision-{market_id}-{side}",
        "market_id": market_id,
        "side": side,
        "decision": "ENTER",
        "paper_enter_allowed": True,
        "opportunity_score": score,
        "blockers_json": [],
        "warnings_json": [],
        "required_to_pass_json": [],
        "policy_json": {},
        "evidence": {},
    }
