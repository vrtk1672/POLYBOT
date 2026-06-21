from __future__ import annotations

from app.services.side_evidence import SideEvidenceScorer


def test_direct_yes_evidence_boosts_yes_only() -> None:
    scorer = SideEvidenceScorer()

    yes = scorer.score_decision(_decision("YES", direction="YES", confidence=0.80)).to_dict()
    no = scorer.score_decision(_decision("NO", direction="YES", confidence=0.80)).to_dict()

    assert yes["side_evidence_score"] > 0
    assert no["side_evidence_score"] < yes["side_evidence_score"]
    assert any("supports YES" in reason for reason in yes["positive_reasons"])
    assert any("supports YES" in reason for reason in no["negative_reasons"])


def test_side_unknown_does_not_create_directional_support() -> None:
    scorer = SideEvidenceScorer()

    yes = scorer.score_decision(_decision("YES", direction="UNKNOWN", confidence=0)).to_dict()
    no = scorer.score_decision(_decision("NO", direction="UNKNOWN", confidence=0)).to_dict()

    assert yes["side_evidence_score"] == no["side_evidence_score"]
    assert yes["direction_confidence"] == 0
    assert "explicit event/source direction" in yes["missing_reasons"]


def _decision(side: str, *, direction: str, confidence: float) -> dict:
    return {
        "market_id": "market-side-evidence",
        "side": side,
        "token_id": f"token-{side}",
        "thesis_state": "THESIS_SUPPORTED",
        "edge_state": "EDGE_SUPPORTED",
        "exit_state": "EXIT_READY",
        "evidence": {
            "side_evidence": {"direction_for_market": direction, "direction_confidence": confidence},
            "orderbook_best_bid": 0.40,
            "orderbook_best_ask": 0.42,
            "orderbook_liquidity_score": 0.80,
        },
    }
