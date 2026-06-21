from __future__ import annotations

from app.services.full_mesh_contract import mesh_response
from app.services.full_mesh_inquiry import FullMeshInquiryOrchestrator
from app.services.full_mesh_registry import registry_by_name
from app.services.source_backed_edge_engine import build_edge_thesis_from_mesh_responses
from app.services.source_organ_runtime import source_organ_status_summary


def _identity() -> dict:
    return {"candidate_id": "candidate-1", "market_id": "m1", "side": "YES", "token_id": "token-yes", "condition_id": "cond1"}


def _bundle() -> dict:
    return {
        **_identity(),
        "bundle_id": "bundle-1",
        "correlation_id": "corr-1",
        "event_id": "event-1",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "correlation_confidence": "HIGH",
        "orderbook": {"snapshot_id": "ob1", "trusted_state": "TRUSTED_FRESH", "freshness_state": "FRESH", "age_seconds": 10},
        "opinions": {},
        "coordinator": {},
    }


def test_source_organ_status_summary_counts_unavailable_and_no_data() -> None:
    responses = [
        mesh_response(
            neuron_name="news",
            neuron_type="NEWS",
            identity=_identity(),
            response_state="UNAVAILABLE",
            reason="missing config",
            summary="missing config",
            blocker_code="NEWS_MISSING_CONFIG",
            metadata={"source_organ": True, "source_organ_runtime_state": "UNAVAILABLE_MISSING_CONFIG", "missing_config_keys": ["NEWS_API_KEY"]},
        ),
        mesh_response(
            neuron_name="social",
            neuron_type="SOCIAL",
            identity=_identity(),
            response_state="MISSING",
            reason="no data",
            summary="no data",
            blocker_code="SOCIAL_NO_DATA",
            metadata={"source_organ": True, "source_organ_runtime_state": "UNAVAILABLE_NO_DATA"},
        ),
    ]

    summary = source_organ_status_summary(responses)

    assert summary["source_organs_requested"] == 2
    assert summary["source_organs_unavailable"] == 1
    assert summary["missing_config_organs"] == ["news"]
    assert summary["no_data_organs"] == ["social"]
    assert summary["missing_config_keys"] == ["NEWS_API_KEY"]


def test_full_mesh_session_exposes_source_status_summary() -> None:
    registry = [registry_by_name()["candidate"], registry_by_name()["cross_market"]]
    session = FullMeshInquiryOrchestrator(registry=registry).build_session(_bundle())

    assert "source_organ_status_summary" in session
    assert "cross_market" in session["source_organ_status_summary"]["organ_statuses"]
    assert session["source_organ_status_summary"]["organ_statuses"]["cross_market"]["state"] == "UNAVAILABLE"
    assert session["source_organ_status_summary"]["source_organs_requested"] == 1


def test_all_source_organs_unavailable_sets_edge_source_unavailable() -> None:
    identity = _identity()
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
            response_state="UNAVAILABLE",
            reason="missing config",
            summary="missing config",
            blocker_code="NEWS_MISSING_CONFIG",
            metadata={"source_organ": True, "source_organ_runtime_state": "UNAVAILABLE_MISSING_CONFIG"},
        ),
    ]

    thesis = build_edge_thesis_from_mesh_responses(identity, responses)

    assert thesis["edge_state"] == "EDGE_SOURCE_ORGANS_UNAVAILABLE"
    assert thesis["source_backed"] is False
    assert thesis["risk_usable"] is False
    assert thesis["source_organ_status"]["unavailable_organs"] == ["news"]
