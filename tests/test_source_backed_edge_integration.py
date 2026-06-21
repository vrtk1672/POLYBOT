from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services import risk_evidence_mesh as risk_mesh
from app.services.source_backed_edge_engine import build_edge_thesis


def _record(**overrides):
    row = {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-edge-1",
        "market_id": "market-edge",
        "condition_id": "condition-edge",
        "side": "YES",
        "token_id": "token-yes",
    }
    row.update(overrides)
    return row


def _book(**overrides):
    row = {
        "orderbook_snapshot_id": "ob-edge",
        "snapshot_status": "OK",
        "is_stale": False,
        "created_at": datetime.now(UTC),
        "best_ask": Decimal("0.42"),
        "best_bid": Decimal("0.40"),
        "spread": Decimal("0.02"),
        "liquidity_score": Decimal("0.80"),
    }
    row.update(overrides)
    return row


def test_candidate_scoped_orderbook_alone_creates_watch_not_fake_edge() -> None:
    thesis = build_edge_thesis(_record(), {"orderbook": _book()})

    assert thesis["edge_state"] == "EDGE_WATCH"
    assert thesis["source_backed"] is False
    assert thesis["risk_usable"] is False
    assert thesis["blocker_code"] in {"NO_SOURCE_BACKED_EDGE", "NO_CURRENT_DIRECTIONAL_EDGE"}


def test_no_directional_source_returns_no_source_backed_edge_or_watch() -> None:
    thesis = build_edge_thesis(_record(), {"orderbook": _book(), "memory": {"market_id": "market-edge", "memory_confidence": 0.9}})

    assert thesis["edge_state"] in {"EDGE_WATCH", "NO_SOURCE_BACKED_EDGE"}
    assert thesis["risk_usable"] is False


def test_source_backed_directional_evidence_creates_supported_edge() -> None:
    thesis = build_edge_thesis(
        _record(),
        {
            "orderbook": _book(),
            "payout": {"evaluation_id": "payout-1", "risk_reward": Decimal("2.0"), "fair_probability": Decimal("0.61"), "confidence": 0.9, "created_at": datetime.now(UTC)},
            "news": {
                "impact_id": "news-1",
                "direction": "YES",
                "strength": Decimal("0.95"),
                "confidence": Decimal("0.95"),
                "already_priced_in": Decimal("0.0"),
                "created_at": datetime.now(UTC),
                "reason": "Fresh source supports YES.",
            },
            "whale": {
                "whale_event_id": "whale-1",
                "side": "YES",
                "size_usd": Decimal("10000"),
                "confidence": Decimal("0.9"),
                "event_time": datetime.now(UTC),
            },
        },
    )

    assert thesis["edge_state"] == "EDGE_SUPPORTED"
    assert thesis["source_backed"] is True
    assert thesis["risk_usable"] is True
    assert thesis["fair_probability_estimate"] is None
    assert thesis["expected_edge"] is None


def test_conflicting_evidence_blocks_supported_edge() -> None:
    thesis = build_edge_thesis(
        _record(),
        {
            "orderbook": _book(),
            "news": {
                "impact_id": "news-1",
                "direction": "YES",
                "strength": Decimal("0.9"),
                "confidence": Decimal("0.9"),
                "already_priced_in": Decimal("0.0"),
                "created_at": datetime.now(UTC),
            },
            "whale": {
                "whale_event_id": "whale-1",
                "side": "NO",
                "size_usd": Decimal("10000"),
                "confidence": Decimal("0.9"),
                "event_time": datetime.now(UTC),
            },
        },
    )

    assert thesis["edge_state"] == "SOURCE_CONFLICT"
    assert thesis["risk_usable"] is False


def test_stale_evidence_does_not_become_risk_usable() -> None:
    stale = datetime.now(UTC) - timedelta(hours=3)
    thesis = build_edge_thesis(
        _record(),
        {
            "orderbook": _book(created_at=stale),
            "news": {
                "impact_id": "news-1",
                "direction": "YES",
                "strength": Decimal("0.9"),
                "confidence": Decimal("0.9"),
                "already_priced_in": Decimal("0.0"),
                "created_at": stale,
            },
        },
    )

    assert thesis["edge_state"] != "EDGE_SUPPORTED"
    assert thesis["risk_usable"] is False


def test_risk_consumes_supported_edge_thesis() -> None:
    result = risk_mesh._classify(
        _record(),
        {
            "orderbook": _book(),
            "payout": {"evaluation_id": "payout-1", "risk_reward": Decimal("2.0"), "fair_probability": Decimal("0.61"), "confidence": 0.9, "created_at": datetime.now(UTC)},
            "news": {
                "impact_id": "news-1",
                "direction": "YES",
                "strength": Decimal("0.95"),
                "confidence": Decimal("0.95"),
                "already_priced_in": Decimal("0.0"),
                "created_at": datetime.now(UTC),
            },
            "whale": {
                "whale_event_id": "whale-1",
                "side": "YES",
                "size_usd": Decimal("10000"),
                "confidence": Decimal("0.9"),
                "event_time": datetime.now(UTC),
            },
        },
    )

    assert result["edge_thesis"]["edge_state"] == "EDGE_SUPPORTED"
    assert result["edge_thesis"]["risk_usable"] is True
    assert result["risk_blocker_subtype"] != "RISK_BLOCKED_NO_SOURCE_BACKED_EDGE"


def test_risk_still_blocks_other_current_rules_with_supported_edge() -> None:
    result = risk_mesh._classify(
        _record(),
        {
            "orderbook": _book(spread=Decimal("0.20")),
            "news": {
                "impact_id": "news-1",
                "direction": "YES",
                "strength": Decimal("0.95"),
                "confidence": Decimal("0.95"),
                "already_priced_in": Decimal("0.0"),
                "created_at": datetime.now(UTC),
            },
        },
    )

    assert result["risk_decision"] == "RISK_BLOCK"
    assert result["risk_blocker_subtype"] == "RISK_BLOCKED_SPREAD"
