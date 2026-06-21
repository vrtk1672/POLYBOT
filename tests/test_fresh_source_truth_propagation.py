from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services import risk_evidence_mesh as risk_mesh
from app.services.source_backed_edge_engine import build_edge_thesis


def _record() -> dict[str, object]:
    return {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-cycle-1",
        "market_id": "market-cycle",
        "condition_id": "condition-cycle",
        "side": "YES",
        "token_id": "token-yes",
    }


def _evidence() -> dict[str, object]:
    return {
        "source_refresh_context": {
            "source_refresh_cycle_id": "source_refresh_cycle_1",
            "source_refresh_completed_at": datetime.now(UTC),
        },
        "orderbook": {
            "orderbook_snapshot_id": "ob-cycle",
            "created_at": datetime.now(UTC),
            "best_ask": Decimal("0.42"),
            "best_bid": Decimal("0.40"),
            "spread": Decimal("0.02"),
            "liquidity_score": Decimal("0.9"),
        },
        "news": {
            "impact_id": "news-cycle",
            "direction": "YES",
            "strength": Decimal("0.98"),
            "confidence": Decimal("0.98"),
            "already_priced_in": Decimal("0.0"),
            "created_at": datetime.now(UTC),
        },
        "whale": {
            "whale_event_id": "whale-cycle",
            "side": "YES",
            "size_usd": Decimal("10000"),
            "confidence": Decimal("0.95"),
            "event_time": datetime.now(UTC),
        },
    }


def test_edge_thesis_records_source_refresh_context() -> None:
    thesis = build_edge_thesis(_record(), _evidence())

    assert thesis["source_refresh_cycle_id"] == "source_refresh_cycle_1"
    assert thesis["propagation_context"]["source_refresh_cycle_id"] == "source_refresh_cycle_1"
    assert thesis["propagation_context"]["candidate_id"] == "candidate-cycle-1"
    assert thesis["fresh_sources_used"]


def test_risk_classification_consumes_edge_from_same_source_refresh_cycle() -> None:
    result = risk_mesh._classify(_record(), _evidence())

    assert result["edge_thesis"]["source_refresh_cycle_id"] == "source_refresh_cycle_1"
    assert result["edge_thesis"]["propagation_context"]["candidate_id"] == "candidate-cycle-1"
    assert result["risk_blocker_subtype"] != "RISK_BLOCKED_EDGE_STALE"
