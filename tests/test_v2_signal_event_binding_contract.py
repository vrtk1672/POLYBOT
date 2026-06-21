from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.neural_mesh.lineage import SignalLineage
from app.services.neuron_signals import rules_status_to_signal, source_status_to_signal


def test_signal_lineage_contract_accepts_reference_only_payload() -> None:
    lineage = SignalLineage(
        signal_id="signal_abc",
        neuron_name="rules",
        producer_name="rules_resolution_adapter",
        producer_component="app.services.neuron_signals",
        source_name="rules_resolution_truth",
        market_id="market-1",
        correlation_id="corr_1",
        raw_payload_ref="rules_analysis:abc",
        generated_from="rules_resolution",
        lineage={"raw_payload_policy": "reference_only"},
    )
    payload = lineage.to_api_dict()
    assert payload["producer_name"] == "rules_resolution_adapter"
    assert payload["raw_payload_ref"] == "rules_analysis:abc"


def test_signal_lineage_requires_producer_name() -> None:
    with pytest.raises(ValidationError):
        SignalLineage(signal_id="signal_abc", neuron_name="rules", producer_name="")


def test_source_status_adapter_adds_correlation_and_ref() -> None:
    signal = source_status_to_signal(
        {
            "source_name": "polymarket_gamma",
            "source_type": "market_discovery",
            "runtime_status": "ACTIVE",
            "freshness_status": "FRESH",
            "configured": True,
            "read_only": True,
            "mutation_allowed": False,
            "details_json": {"sample_market_id": "m1"},
        }
    )
    assert signal.correlation_id
    assert signal.raw_payload_ref == "source_status:polymarket_gamma"


def test_rules_adapter_adds_correlation_and_ref() -> None:
    signal = rules_status_to_signal(
        {
            "market_id": "m1",
            "rules_analysis_id": "ra1",
            "resolution_source_status": "AMBIGUOUS",
            "source_verification_status": "WARNING",
        }
    )
    assert signal.correlation_id
    assert signal.raw_payload_ref == "rules_analysis:ra1"
