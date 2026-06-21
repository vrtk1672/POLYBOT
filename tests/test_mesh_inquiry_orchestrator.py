from __future__ import annotations

from app.services.full_mesh_contract import mesh_response
from app.services.full_mesh_inquiry import FullMeshInquiryOrchestrator
from app.services.source_backed_edge_engine import build_edge_thesis_from_mesh_responses


def _bundle() -> dict:
    return {
        "bundle_id": "mesh_bundle_corr-1",
        "candidate_id": "candidate-1",
        "market_id": "m1",
        "condition_id": "cond1",
        "side": "YES",
        "token_id": "token-yes",
        "correlation_id": "corr-1",
        "event_id": "event-1",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "correlation_confidence": "HIGH",
        "orderbook": {
            "snapshot_id": "ob1",
            "trusted_state": "TRUSTED_FRESH",
            "freshness_state": "FRESH",
            "age_seconds": 8,
            "best_bid": 0.31,
            "best_ask": 0.35,
            "spread": 0.04,
        },
        "opinions": {
            "liquidity": {"state": "PRESENT", "summary": "liquidity ok"},
            "risk": {"state": "PRESENT", "summary": "risk present"},
            "exit": {"state": "PRESENT", "summary": "exit present"},
            "capital": {"capital_opinion_state": "CAPITAL_OK", "summary": "capital ok"},
            "lifecycle": {"lifecycle_opinion_state": "LIFECYCLE_ALLOWED", "summary": "lifecycle ok"},
        },
        "coordinator": {"decision": "PRICE_READY", "reason": "all reacted", "decision_id": "coord1"},
    }


def test_candidate_scoped_bundle_creates_mesh_inquiry_session() -> None:
    session = FullMeshInquiryOrchestrator().build_session(
        _bundle(),
        edge={"edge_state": "EDGE_WATCH", "edge_score": 0.18, "source_backed": False, "risk_usable": False, "blocker_code": "NO_SOURCE_BACKED_EDGE"},
        actionability={"candidate_paper_actionability_state": "BLOCKED_BY_RISK", "blockers": ["BLOCKED_BY_RISK"]},
    )

    assert session["mesh_session_id"].startswith("full_mesh_inquiry_")
    assert session["candidate_id"] == "candidate-1"
    assert session["neurons_requested"] > 10
    assert session["neurons_responded"] > 0
    assert "cross_market" in session["missing_neurons"]
    assert session["inquiry_state"] == "BLOCKED"
    assert session["edge_state"] == "EDGE_WATCH"


def test_every_organ_response_receives_candidate_identity() -> None:
    session = FullMeshInquiryOrchestrator().build_session(_bundle())

    for response in session["responses"]:
        assert response["candidate_id"] == "candidate-1"
        assert response["market_id"] == "m1"
        assert response["side"] == "YES"
        assert response["token_id"] == "token-yes"


def test_orderbook_only_mesh_responses_create_watch_not_supported_edge() -> None:
    identity = {"candidate_id": "candidate-1", "market_id": "m1", "side": "YES", "token_id": "token-yes"}
    responses = [
        mesh_response(
            neuron_name="trusted_orderbook",
            neuron_type="ORDERBOOK",
            identity=identity,
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
    ]

    thesis = build_edge_thesis_from_mesh_responses(identity, responses)

    assert thesis["edge_state"] == "EDGE_WATCH"
    assert thesis["source_backed"] is False
    assert thesis["risk_usable"] is False


def test_directional_source_mesh_response_can_create_supported_edge() -> None:
    identity = {"candidate_id": "candidate-1", "market_id": "m1", "side": "YES", "token_id": "token-yes"}
    responses = [
        mesh_response(
            neuron_name="trusted_orderbook",
            neuron_type="ORDERBOOK",
            identity=identity,
            response_state="WATCH",
            supports_side="YES",
            confidence=0.7,
            strength=0.3,
            freshness_seconds=10,
            source_backed=True,
            summary="fresh orderbook",
            reason="fresh orderbook",
            source_records=[{"source_record_id": "ob1"}],
        ),
        mesh_response(
            neuron_name="news",
            neuron_type="NEWS",
            identity=identity,
            response_state="SUPPORTED",
            supports_side="YES",
            confidence=0.95,
            strength=0.9,
            freshness_seconds=30,
            source_backed=True,
            summary="fresh directional news",
            reason="fresh source-backed news supports YES",
            source_records=[{"source_record_id": "news1"}],
        ),
    ]

    thesis = build_edge_thesis_from_mesh_responses(identity, responses)

    assert thesis["edge_state"] == "EDGE_SUPPORTED"
    assert thesis["source_backed"] is True
    assert thesis["risk_usable"] is True
    assert "news" in thesis["supporting_neurons"]
