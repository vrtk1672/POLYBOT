from __future__ import annotations

from app.services.same_market_arbitration import SameMarketSideArbitrator


def test_same_market_opposing_enters_do_not_both_reach_gate_at_high_defense() -> None:
    decisions = [
        _decision("market-same", "YES", 61.99),
        _decision("market-same", "NO", 61.99),
    ]

    result = SameMarketSideArbitrator(defense_level=100).arbitrate(decisions)

    assert all(item["paper_enter_allowed"] is False for item in result)
    assert all(item["decision"] == "BLOCK" for item in result)
    assert all("SAME_MARKET_OPPOSING_SIDE_UNRESOLVED" in item["blockers_json"] for item in result)
    assert all("SAME_MARKET_OPPOSING_ENTER_CONFLICT" in item["blockers_json"] for item in result)


def test_defense_zero_tie_uses_deterministic_tie_breaker() -> None:
    decisions = [
        _decision("market-zero-tie", "YES", 50.0),
        _decision("market-zero-tie", "NO", 50.0),
    ]

    result = SameMarketSideArbitrator(defense_level=0).arbitrate(decisions)
    enters = [item for item in result if item["decision"] == "ENTER"]

    assert len(enters) == 1
    assert enters[0]["evidence"]["same_market_side_arbitration"]["tie_breaker_used"] == "deterministic_hash_market_session"


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
