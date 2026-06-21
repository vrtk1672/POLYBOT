from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.source_backed_edge_engine import build_edge_thesis


def _record() -> dict[str, object]:
    return {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-prop-1",
        "market_id": "market-prop",
        "condition_id": "condition-prop",
        "side": "YES",
        "token_id": "token-yes",
    }


def _book(ts: datetime | None = None) -> dict[str, object]:
    return {
        "orderbook_snapshot_id": "ob-prop",
        "created_at": ts or datetime.now(UTC),
        "best_ask": Decimal("0.42"),
        "best_bid": Decimal("0.40"),
        "spread": Decimal("0.02"),
        "liquidity_score": Decimal("0.90"),
    }


def test_stale_payout_does_not_poison_fresh_supported_sources() -> None:
    stale = datetime.now(UTC) - timedelta(days=5)
    thesis = build_edge_thesis(
        _record(),
        {
            "orderbook": _book(),
            "payout": {"evaluation_id": "old-payout", "risk_reward": Decimal("2.0"), "confidence": 0.9, "created_at": stale},
            "news": {"impact_id": "fresh-news", "direction": "YES", "strength": Decimal("0.98"), "confidence": Decimal("0.98"), "already_priced_in": Decimal("0.0"), "created_at": datetime.now(UTC)},
            "whale": {"whale_event_id": "fresh-whale", "side": "YES", "size_usd": Decimal("10000"), "confidence": Decimal("0.95"), "event_time": datetime.now(UTC)},
        },
    )

    assert thesis["edge_state"] == "EDGE_SUPPORTED"
    assert thesis["risk_usable"] is True
    assert any(item["source_record_id"] == "payout_odds_evaluations:old-payout" for item in thesis["stale_sources_ignored"])


def test_stale_payout_blocks_when_it_is_only_directional_source() -> None:
    stale = datetime.now(UTC) - timedelta(days=5)
    thesis = build_edge_thesis(_record(), {"orderbook": _book(), "payout": {"evaluation_id": "old-payout", "risk_reward": Decimal("2.0"), "confidence": 0.9, "created_at": stale}})

    assert thesis["edge_state"] == "EDGE_STALE"
    assert thesis["risk_usable"] is False
    assert thesis["stale_sources_blocking"]


def test_fresh_derived_signals_are_watch_only_not_fake_supported() -> None:
    thesis = build_edge_thesis(
        _record(),
        {
            "orderbook": _book(),
            "mesh_responses": [
                {
                    "neuron_name": "market_movement",
                    "neuron_type": "SIGNAL",
                    "candidate_id": "candidate-prop-1",
                    "market_id": "market-prop",
                    "side": "YES",
                    "token_id": "token-yes",
                    "response_state": "WATCH",
                    "supports_side": "NEUTRAL",
                    "confidence": 0.8,
                    "strength": 0.7,
                    "freshness_seconds": 10,
                    "source_records": [{"source_record_id": "market_technical_signals:1"}],
                    "metadata": {"source_organ": True, "candidate_link_state": "CANDIDATE_LINKED"},
                }
            ],
        },
    )

    assert thesis["edge_state"] in {"DERIVED_SIGNALS_WATCH_ONLY", "EDGE_WATCH"}
    assert thesis["risk_usable"] is False
    assert thesis["source_backed"] is False
