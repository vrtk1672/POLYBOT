from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services import risk_evidence_mesh as risk_mesh


def _fresh_orderbook() -> dict:
    return {
        "snapshot_status": "OK",
        "is_stale": False,
        "created_at": datetime.now(UTC),
        "best_ask": Decimal("0.42"),
        "best_bid": Decimal("0.40"),
        "spread": Decimal("0.02"),
        "liquidity_score": Decimal("0.75"),
    }


def test_risk_lineage_complete_candidate_identity_is_not_lineage_critical() -> None:
    record = {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-1",
        "market_id": "market-1",
        "condition_id": "condition-1",
        "side": "YES",
        "token_id": "token-yes",
    }
    result = risk_mesh._classify(
        record,
        {
            "orderbook": _fresh_orderbook(),
            "payout": {"risk_reward": Decimal("1.2"), "fair_probability": Decimal("0.55")},
            "capital_efficiency": {"recommendation": "CAPITAL_SUPPORT", "capital_efficiency_score": Decimal("0.7")},
        },
    )

    assert "CONDITION_ID_MISSING" not in result["critical_evidence_missing_json"]
    assert "TOKEN_MISSING" not in result["critical_evidence_missing_json"]
    assert result["risk_blocker_subtype"] != "RISK_BLOCKED_LINEAGE_CRITICAL"


def test_risk_lineage_missing_token_remains_critical() -> None:
    record = {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-1",
        "market_id": "market-1",
        "condition_id": "condition-1",
        "side": "YES",
        "token_id": None,
    }
    result = risk_mesh._classify(record, {"orderbook": _fresh_orderbook()})

    assert "TOKEN_MISSING" in result["critical_evidence_missing_json"]
    assert result["risk_decision"] == "RISK_BLOCK"
    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_LINEAGE_CRITICAL"
