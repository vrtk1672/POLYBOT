from __future__ import annotations

import pytest

from app.services.full_mesh_contract import mesh_response, validate_mesh_response
from app.services.full_mesh_registry import DECISION_CRITICAL_ORGANS, EXPLICITLY_EXEMPT_ORGANS, registry_by_name, validate_decision_critical_coverage


def test_universal_mesh_contract_requires_common_shape() -> None:
    response = mesh_response(
        neuron_name="orderbook",
        neuron_type="ORDERBOOK",
        identity={
            "candidate_id": "candidate-1",
            "market_id": "m1",
            "condition_id": "c1",
            "side": "YES",
            "token_id": "t1",
            "correlation_id": "corr-1",
            "event_id": "event-1",
        },
        response_state="WATCH",
        supports_side="YES",
        confidence=0.7,
        strength=0.3,
        freshness_seconds=12,
        source_backed=True,
        summary="Orderbook is fresh.",
        reason="Trusted candidate-scoped orderbook exists.",
        source_records=[{"source_type": "orderbook_snapshot", "source_record_id": "ob1"}],
    )

    assert validate_mesh_response(response) == response
    assert response["candidate_id"] == "candidate-1"
    assert response["supports_side"] == "YES"
    assert response["source_records"][0]["source_record_id"] == "ob1"


def test_universal_mesh_contract_rejects_invalid_numeric_bounds() -> None:
    with pytest.raises(ValueError):
        validate_mesh_response(
            {
                "neuron_name": "risk",
                "neuron_type": "RISK",
                "candidate_id": "c",
                "market_id": "m",
                "condition_id": None,
                "side": "YES",
                "token_id": "t",
                "correlation_id": "corr",
                "event_id": "event",
                "response_state": "SUPPORTED",
                "supports_side": "YES",
                "confidence": 1.4,
                "strength": 0.1,
                "source_backed": True,
                "summary": "",
                "reason": "",
                "blocker_code": None,
                "required_to_pass": [],
                "source_records": [],
                "created_at": "2026-06-15T00:00:00+00:00",
            }
        )


def test_decision_critical_organs_are_registered_or_exempt() -> None:
    coverage = validate_decision_critical_coverage()

    assert coverage["status"] == "OK"
    assert coverage["missing"] == []
    assert DECISION_CRITICAL_ORGANS.difference(registry_by_name()).difference(EXPLICITLY_EXEMPT_ORGANS) == set()


def test_future_governance_rule_has_explicit_execution_exemptions() -> None:
    assert "paper_execution" in EXPLICITLY_EXEMPT_ORGANS
    assert "live_execution" in EXPLICITLY_EXEMPT_ORGANS
    assert "forbidden" in EXPLICITLY_EXEMPT_ORGANS["live_execution"].lower()
