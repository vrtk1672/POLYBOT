from __future__ import annotations

from datetime import UTC, datetime

from app.data_foundation.orderbook_snapshotter import OrderbookSnapshotter
from app.events.consumers.orderbook_mesh_consumer import OrderbookMeshProofConsumer
from app.services.trusted_orderbook import _missing_candidate_scope


class _EventStore:
    def __init__(self) -> None:
        self.events = []

    def append_event(self, conn, envelope) -> None:
        self.events.append(envelope)


def test_candidate_targeted_snapshot_event_carries_candidate_id() -> None:
    snapshot = OrderbookSnapshotter().normalize_orderbook(
        {"bids": [{"price": "0.40", "size": "10"}], "asks": [{"price": "0.42", "size": "10"}]},
        market_id="market-candidate-scoped",
        token_id="token-yes",
        side="YES",
        source="polymarket_clob_candidate_recovery",
        correlation_id="candidate-refresh-run",
        collected_at=datetime.now(UTC),
        metadata_json={
            "candidate_id": "candidate-123",
            "candidate_source": "paper_eligibility_candidates",
            "refresh_reason": "candidate_targeted_price_path",
            "refresh_scope": "CANDIDATE_SCOPED",
            "source_service": "TrustedOrderbookEvidenceService",
            "candidate_event_scope": "CANDIDATE_TARGETED_REFRESH",
            "candidate_event_scoped": True,
        },
    )
    row = {
        "id": 1,
        "market_id": snapshot.market_id,
        "token_id": snapshot.token_id,
        "side": snapshot.side,
        "orderbook_snapshot_id": snapshot.orderbook_snapshot_id,
        "best_bid": snapshot.best_bid,
        "best_ask": snapshot.best_ask,
        "spread": snapshot.spread,
        "depth_1c": snapshot.depth_1c,
        "depth_2c": snapshot.depth_2c,
        "depth_5c": snapshot.depth_5c,
        "total_bid_depth": snapshot.total_bid_depth,
        "total_ask_depth": snapshot.total_ask_depth,
        "collected_at": snapshot.collected_at,
        "source": snapshot.source,
        "metadata_json": snapshot.metadata_json,
    }
    consumer = OrderbookMeshProofConsumer()
    consumer._events = _EventStore()

    event = consumer._publish_orderbook_event(None, snapshot, row)

    assert event.payload["candidate_id"] == "candidate-123"
    assert event.payload["candidate_source"] == "paper_eligibility_candidates"
    assert event.payload["refresh_reason"] == "candidate_targeted_price_path"
    assert event.payload["refresh_scope"] == "CANDIDATE_SCOPED"
    assert event.payload["source_service"] == "TrustedOrderbookEvidenceService"
    assert event.payload["candidate_event_scope"] == "CANDIDATE_TARGETED_REFRESH"
    assert event.payload["candidate_event_scoped"] is True
    assert event.payload["candidate_link_blocker"] is None
    assert event.payload["market_id"] == "market-candidate-scoped"
    assert event.payload["side"] == "YES"
    assert event.payload["token_id"] == "token-yes"


def test_fresh_market_level_book_still_requires_candidate_scoped_refresh() -> None:
    book = {
        "snapshot_status": "OK",
        "is_stale": False,
        "age_seconds": 10,
        "metadata_json": {"refresh_scope": "MARKET_SCOPED"},
    }

    assert _missing_candidate_scope(book, candidate_id="candidate-123") is True


def test_fresh_same_candidate_book_does_not_require_candidate_scoped_refresh() -> None:
    book = {
        "snapshot_status": "OK",
        "is_stale": False,
        "age_seconds": 10,
        "metadata_json": {
            "candidate_id": "candidate-123",
            "refresh_scope": "CANDIDATE_SCOPED",
        },
    }

    assert _missing_candidate_scope(book, candidate_id="candidate-123") is False
