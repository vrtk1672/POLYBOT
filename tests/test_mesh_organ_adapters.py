from __future__ import annotations

from app.services.full_mesh_contract import identity_from_bundle, validate_mesh_response
from app.services.full_mesh_registry import registry_by_name
from app.services.mesh_organ_adapters import query_organ


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
            "age_seconds": 10,
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


def test_orderbook_adapter_returns_candidate_scoped_response() -> None:
    reg = registry_by_name()["trusted_orderbook"]
    response = query_organ(reg, identity=identity_from_bundle(_bundle()), bundle=_bundle())

    validate_mesh_response(response)
    assert response["neuron_name"] == "trusted_orderbook"
    assert response["candidate_id"] == "candidate-1"
    assert response["response_state"] == "WATCH"
    assert response["source_records"][0]["source_record_id"] == "ob1"


def test_risk_adapter_consumes_edge_thesis() -> None:
    reg = registry_by_name()["risk"]
    edge = {
        "edge_state": "EDGE_SUPPORTED",
        "edge_score": 0.82,
        "source_backed": True,
        "risk_usable": True,
        "supporting_neurons": ["news"],
        "source_records": [{"source_record_id": "news:1"}],
        "edge_thesis_id": "edge1",
    }
    response = query_organ(reg, identity=identity_from_bundle(_bundle()), bundle=_bundle(), edge=edge)

    validate_mesh_response(response)
    assert response["response_state"] == "SUPPORTED"
    assert response["source_backed"] is True
    assert response["metadata"]["edge_thesis_id"] == "edge1"


def test_unavailable_organs_are_recorded_not_hidden() -> None:
    reg = registry_by_name()["cross_market"]
    response = query_organ(reg, identity=identity_from_bundle(_bundle()), bundle=_bundle())

    validate_mesh_response(response)
    assert response["response_state"] == "UNAVAILABLE"
    assert response["blocker_code"] == "CROSS_MARKET_UNAVAILABLE"
