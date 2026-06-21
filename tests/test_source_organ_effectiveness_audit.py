from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.services import risk_evidence_mesh as risk_mesh
from app.services.full_mesh_contract import mesh_response
from app.services.source_backed_edge_engine import build_edge_thesis


def _record() -> dict[str, object]:
    return {
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-source-audit",
        "market_id": "market-source-audit",
        "condition_id": "condition-source-audit",
        "side": "YES",
        "token_id": "token-yes",
    }


def _orderbook() -> dict[str, object]:
    return {
        "orderbook_snapshot_id": "ob-source-audit",
        "snapshot_status": "OK",
        "is_stale": False,
        "created_at": datetime.now(UTC),
        "best_ask": Decimal("0.42"),
        "best_bid": Decimal("0.40"),
        "spread": Decimal("0.02"),
        "liquidity_score": Decimal("0.80"),
    }


def _source_response(*, linked: bool = True, freshness_seconds: int = 10) -> dict[str, object]:
    return mesh_response(
        neuron_name="signal_quality",
        neuron_type="SIGNAL",
        identity={
            "candidate_id": "candidate-source-audit",
            "market_id": "market-source-audit",
            "condition_id": "condition-source-audit",
            "side": "YES",
            "token_id": "token-yes",
            "correlation_id": "corr-source-audit",
            "event_id": "event-source-audit",
        },
        response_state="SUPPORTED",
        supports_side="YES",
        confidence=0.95,
        strength=0.95,
        freshness_seconds=freshness_seconds,
        source_backed=True,
        summary="Fixture directional source supports candidate side.",
        reason="Fixture source response is candidate linked.",
        source_records=[{"source_type": "neuron_signals", "source_record_id": "signal-source-audit"}],
        metadata={
            "source_organ": True,
            "source_organ_runtime_state": "ACTIVE_CANDIDATE_SCOPED" if linked else "ACTIVE_MARKET_LEVEL_ONLY",
            "candidate_link_state": "CANDIDATE_LINKED_MARKET_SIDE" if linked else "MARKET_LEVEL_ONLY",
        },
    )


def test_candidate_linked_source_response_affects_edge_thesis_and_risk() -> None:
    evidence = {"orderbook": _orderbook(), "mesh_responses": [_source_response(linked=True)]}

    thesis = build_edge_thesis(_record(), evidence)
    classified = risk_mesh._classify(_record(), evidence)

    assert thesis["edge_state"] == "EDGE_SUPPORTED"
    assert thesis["risk_usable"] is True
    assert thesis["supporting_neurons"] == ["signal_quality"]
    assert classified["edge_thesis"]["edge_state"] == "EDGE_SUPPORTED"
    assert classified["risk_blocker_subtype"] != "RISK_BLOCKED_NO_SOURCE_BACKED_EDGE"


def test_market_level_source_response_does_not_create_fake_supported_edge() -> None:
    thesis = build_edge_thesis(_record(), {"orderbook": _orderbook(), "mesh_responses": [_source_response(linked=False)]})

    assert thesis["edge_state"] == "EDGE_WATCH"
    assert thesis["source_backed"] is False
    assert thesis["risk_usable"] is False


def test_stale_source_response_is_classified_as_stale_not_supported() -> None:
    thesis = build_edge_thesis(_record(), {"orderbook": _orderbook(), "mesh_responses": [_source_response(linked=True, freshness_seconds=2000)]})

    assert thesis["edge_state"] == "EDGE_STALE"
    assert thesis["risk_usable"] is False

