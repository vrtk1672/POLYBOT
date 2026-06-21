from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import rules_status_to_signal, source_status_to_signal


def test_create_valid_signal_without_market_id() -> None:
    signal = NeuronSignal(
        neuron="market",
        event_type="source_status_observed",
        source_name="polymarket_gamma",
        status="ACTIVE",
        raw_direction="neutral",
        strength=1.0,
        confidence=0.9,
        source_reliability=1.0,
        evidence={"runtime_status": "ACTIVE"},
    )

    assert signal.signal_id.startswith("signal_")
    assert signal.market_id is None
    assert signal.to_api_dict()["status"] == "ACTIVE"


def test_reject_invalid_strength_outside_range() -> None:
    with pytest.raises(ValidationError):
        NeuronSignal(neuron="market", event_type="observed", status="ACTIVE", strength=1.2)
    with pytest.raises(ValidationError):
        NeuronSignal(neuron="market", event_type="observed", status="ACTIVE", strength=-0.1)


def test_reject_missing_neuron() -> None:
    with pytest.raises(ValidationError):
        NeuronSignal(neuron="", event_type="observed", status="ACTIVE")


def test_reject_missing_event_type() -> None:
    with pytest.raises(ValidationError):
        NeuronSignal(neuron="market", event_type="", status="ACTIVE")


def test_signal_contract_has_no_trade_action_fields() -> None:
    signal = NeuronSignal(neuron="rules", event_type="rules_resolution_status_observed", status="DEGRADED")
    payload = signal.to_api_dict()

    for forbidden in ("buy", "sell", "enter_trade", "exit_trade", "trade_decision", "approved", "rejected"):
        assert forbidden not in payload


def test_reject_decision_keys_in_evidence() -> None:
    with pytest.raises(ValidationError):
        NeuronSignal(
            neuron="market",
            event_type="unsafe_payload",
            status="ACTIVE",
            evidence={"buy": True},
        )


def test_source_status_adapter_creates_neutral_signal() -> None:
    signal = source_status_to_signal(
        {
            "source_name": "polymarket_clob_orderbook",
            "source_type": "orderbook",
            "configured": True,
            "runtime_status": "ACTIVE",
            "freshness_status": "FRESH",
            "read_only": True,
            "mutation_allowed": False,
            "latency_ms": 12,
            "details_json": {"sample_market_id": "market-1"},
        }
    )

    assert signal.neuron == "orderbook"
    assert signal.event_type == "source_status_observed"
    assert signal.market_id == "market-1"
    assert signal.raw_direction == "neutral"
    assert signal.status == "ACTIVE"
    assert "trade_decision" not in signal.evidence


def test_rules_adapter_creates_neutral_resolution_signal() -> None:
    signal = rules_status_to_signal(
        {
            "market_id": "market-2",
            "question": "Example market?",
            "resolution_source_status": "AMBIGUOUS",
            "resolution_source_confidence": 0.55,
            "penalty": 0.35,
            "rules_text_present": True,
        }
    )

    assert signal.neuron == "rules"
    assert signal.event_type == "rules_resolution_status_observed"
    assert signal.market_id == "market-2"
    assert signal.raw_direction == "neutral"
    assert signal.status == "DEGRADED"
