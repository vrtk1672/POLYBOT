from __future__ import annotations

from app.services.paper_runtime_decisions import _arbitrate_same_market_opposing_enters


def test_equal_opposing_enter_decisions_are_demoted_before_gate() -> None:
    decisions = [
        _decision("market-arb", "YES", 61.99),
        _decision("market-arb", "NO", 61.99),
        _decision("market-other", "YES", 62.5),
    ]

    result = _arbitrate_same_market_opposing_enters(decisions)
    by_pair = {(item["market_id"], item["side"]): item for item in result}

    assert by_pair[("market-arb", "YES")]["decision"] == "BLOCK"
    assert by_pair[("market-arb", "NO")]["decision"] == "BLOCK"
    assert "SAME_MARKET_OPPOSING_ENTER_CONFLICT" in by_pair[("market-arb", "YES")]["blockers_json"]
    assert "SAME_MARKET_OPPOSING_ENTER_CONFLICT" in by_pair[("market-arb", "NO")]["blockers_json"]
    assert by_pair[("market-other", "YES")]["decision"] == "ENTER"


def test_stronger_side_wins_opposing_enter_arbitration() -> None:
    decisions = [_decision("market-arb", "YES", 63), _decision("market-arb", "NO", 61)]

    result = _arbitrate_same_market_opposing_enters(decisions)
    yes = next(item for item in result if item["side"] == "YES")
    no = next(item for item in result if item["side"] == "NO")

    assert yes["decision"] == "ENTER"
    assert yes["paper_enter_allowed"] is True
    assert no["decision"] == "BLOCK"
    assert no["paper_enter_allowed"] is False
    assert "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION" in no["blockers_json"]


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
