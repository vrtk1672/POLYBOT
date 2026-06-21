from __future__ import annotations

from app.services.same_market_arbitration import SameMarketSideArbitrator


def test_defense_100_requires_large_margin() -> None:
    decisions = [_decision("market-margin", "YES", 64.0), _decision("market-margin", "NO", 61.0)]

    result = SameMarketSideArbitrator(defense_level=100).arbitrate(decisions)

    assert all(item["decision"] == "BLOCK" for item in result)
    assert all("SAME_MARKET_OPPOSING_SIDE_UNRESOLVED" in item["blockers_json"] for item in result)


def test_defense_20_allows_smaller_margin() -> None:
    decisions = [_decision("market-margin-low", "YES", 64.0), _decision("market-margin-low", "NO", 61.0)]

    result = SameMarketSideArbitrator(defense_level=20).arbitrate(decisions)
    yes = next(item for item in result if item["side"] == "YES")
    no = next(item for item in result if item["side"] == "NO")

    assert yes["decision"] == "ENTER"
    assert yes["paper_enter_allowed"] is True
    assert no["decision"] == "BLOCK"
    assert "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION" in no["blockers_json"]


def test_integrity_blocker_prevents_side_from_winning() -> None:
    decisions = [
        _decision("market-integrity", "YES", 80.0, blockers=["MISSING_TOKEN_ID"]),
        _decision("market-integrity", "NO", 50.0),
    ]

    result = SameMarketSideArbitrator(defense_level=20).arbitrate(decisions)
    yes = next(item for item in result if item["side"] == "YES")
    no = next(item for item in result if item["side"] == "NO")

    assert no["decision"] == "ENTER"
    assert yes["decision"] == "BLOCK"
    assert "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION" in yes["blockers_json"]


def _decision(market_id: str, side: str, score: float, blockers: list[str] | None = None) -> dict:
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
        "blockers_json": blockers or [],
        "warnings_json": [],
        "required_to_pass_json": [],
        "policy_json": {},
        "evidence": {
            "orderbook_age_seconds": 5,
            "orderbook_ttl_seconds": 60,
            "orderbook_best_bid": 0.40,
            "orderbook_best_ask": 0.42,
            "source_evidence": {
                "edge_state": "EDGE_SUPPORTED",
                "thesis_state": "THESIS_SUPPORTED",
                "exit_state": "EXIT_READY",
            },
        },
    }
