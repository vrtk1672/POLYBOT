from __future__ import annotations

from app.services.same_market_arbitration import SameMarketSideArbitrator


def test_side_evidence_selects_supported_side() -> None:
    result = SameMarketSideArbitrator(defense_level=20).arbitrate(
        [
            _decision("YES", direction="YES", confidence=0.80),
            _decision("NO", direction="YES", confidence=0.80),
        ]
    )
    yes = next(item for item in result if item["side"] == "YES")
    no = next(item for item in result if item["side"] == "NO")

    assert yes["decision"] == "ENTER"
    assert no["decision"] == "BLOCK"
    assert "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION" in no["blockers_json"]
    assert yes["policy_json"]["same_market_side_arbitration"]["outcome"] == "ARBITRATION_SELECTED_BY_SIDE_EVIDENCE"


def test_better_orderbook_can_break_close_tie() -> None:
    result = SameMarketSideArbitrator(defense_level=20).arbitrate(
        [
            _decision("YES", bid=0.40, ask=0.41, liquidity=0.95),
            _decision("NO", bid=0.40, ask=0.50, liquidity=0.50),
        ]
    )
    yes = next(item for item in result if item["side"] == "YES")

    assert yes["decision"] == "ENTER"
    assert yes["policy_json"]["same_market_side_arbitration"]["selected_side"] == "YES"


def _decision(
    side: str,
    *,
    direction: str = "UNKNOWN",
    confidence: float = 0,
    bid: float = 0.40,
    ask: float = 0.42,
    liquidity: float = 0.80,
) -> dict:
    return {
        "decision_id": f"decision-side-evidence-{side}",
        "market_id": "market-side-evidence-arb",
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
            "side_evidence": {"direction_for_market": direction, "direction_confidence": confidence},
            "orderbook_best_bid": bid,
            "orderbook_best_ask": ask,
            "orderbook_liquidity_score": liquidity,
            "orderbook_age_seconds": 5,
            "orderbook_ttl_seconds": 60,
        },
    }
