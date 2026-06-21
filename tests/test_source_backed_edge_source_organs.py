from __future__ import annotations

from app.services.full_mesh_contract import mesh_response
from app.services.source_backed_edge_engine import build_edge_thesis_from_mesh_responses


def _identity() -> dict:
    return {"candidate_id": "candidate-1", "market_id": "m1", "side": "YES", "token_id": "token-yes", "condition_id": "cond1"}


def _orderbook() -> dict:
    return mesh_response(
        neuron_name="trusted_orderbook",
        neuron_type="ORDERBOOK",
        identity=_identity(),
        response_state="WATCH",
        supports_side="YES",
        confidence=0.7,
        strength=0.3,
        freshness_seconds=10,
        source_backed=True,
        summary="fresh orderbook",
        reason="fresh orderbook",
        source_records=[{"source_record_id": "ob1"}],
    )


def test_no_directional_source_keeps_orderbook_only_at_watch() -> None:
    thesis = build_edge_thesis_from_mesh_responses(
        _identity(),
        [
            _orderbook(),
            mesh_response(
                neuron_name="news",
                neuron_type="NEWS",
                identity=_identity(),
                response_state="MISSING",
                reason="no data",
                summary="no data",
                blocker_code="NEWS_NO_DATA",
                metadata={"source_organ": True, "source_organ_runtime_state": "UNAVAILABLE_NO_DATA"},
            ),
        ],
    )

    assert thesis["edge_state"] == "EDGE_WATCH"
    assert thesis["source_backed"] is False
    assert thesis["risk_usable"] is False


def test_candidate_linked_directional_source_can_support_edge() -> None:
    thesis = build_edge_thesis_from_mesh_responses(
        _identity(),
        [
            _orderbook(),
            mesh_response(
                neuron_name="signal_quality",
                neuron_type="SIGNAL",
                identity=_identity(),
                response_state="SUPPORTED",
                supports_side="YES",
                confidence=0.96,
                strength=0.9,
                freshness_seconds=20,
                source_backed=True,
                summary="candidate-linked signal",
                reason="signal supports candidate side",
                source_records=[{"source_record_id": "signal-1"}],
                metadata={"source_organ": True, "source_organ_runtime_state": "ACTIVE_CANDIDATE_SCOPED", "candidate_link_state": "CANDIDATE_LINKED_MARKET_SIDE"},
            ),
        ],
    )

    assert thesis["edge_state"] == "EDGE_SUPPORTED"
    assert thesis["source_backed"] is True
    assert thesis["risk_usable"] is True
    assert "signal_quality" in thesis["supporting_neurons"]


def test_market_level_only_directional_source_does_not_create_supported_edge() -> None:
    thesis = build_edge_thesis_from_mesh_responses(
        _identity(),
        [
            _orderbook(),
            mesh_response(
                neuron_name="news",
                neuron_type="NEWS",
                identity=_identity(),
                response_state="SUPPORTED",
                supports_side="YES",
                confidence=0.99,
                strength=1.0,
                freshness_seconds=10,
                source_backed=True,
                summary="market-level only news",
                reason="not candidate linked",
                source_records=[{"source_record_id": "news-1"}],
                metadata={"source_organ": True, "source_organ_runtime_state": "ACTIVE_MARKET_LEVEL_ONLY", "candidate_link_state": "MARKET_LEVEL_ONLY"},
            ),
        ],
    )

    assert thesis["edge_state"] == "EDGE_WATCH"
    assert thesis["source_backed"] is False
    assert thesis["risk_usable"] is False


def test_conflicting_source_organ_response_blocks_edge() -> None:
    thesis = build_edge_thesis_from_mesh_responses(
        _identity(),
        [
            _orderbook(),
            mesh_response(
                neuron_name="news",
                neuron_type="NEWS",
                identity=_identity(),
                response_state="SUPPORTED",
                supports_side="YES",
                confidence=0.95,
                strength=0.9,
                freshness_seconds=10,
                source_backed=True,
                summary="supporting news",
                reason="supports",
                source_records=[{"source_record_id": "news-1"}],
                metadata={"source_organ": True, "source_organ_runtime_state": "ACTIVE_CANDIDATE_SCOPED", "candidate_link_state": "CANDIDATE_LINKED_MARKET_SIDE"},
            ),
            mesh_response(
                neuron_name="whale",
                neuron_type="WHALE",
                identity=_identity(),
                response_state="OPPOSED",
                supports_side="NO",
                confidence=0.95,
                strength=0.9,
                freshness_seconds=10,
                source_backed=True,
                summary="opposing whale",
                reason="opposes",
                source_records=[{"source_record_id": "whale-1"}],
                metadata={"source_organ": True, "source_organ_runtime_state": "ACTIVE_CANDIDATE_SCOPED", "candidate_link_state": "CANDIDATE_LINKED_MARKET_SIDE"},
            ),
        ],
    )

    assert thesis["edge_state"] == "SOURCE_CONFLICT"
    assert thesis["risk_usable"] is False
