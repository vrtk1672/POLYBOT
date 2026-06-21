from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.neural_mesh.registry import DEFAULT_NEURONS, REQUIRED_NEURON_NAMES, NeuronHealth, NeuronRegistryEntry


def test_default_neurons_include_required_names() -> None:
    names = {item.neuron_name for item in DEFAULT_NEURONS}
    assert REQUIRED_NEURON_NAMES <= names


def test_registry_entry_requires_name() -> None:
    with pytest.raises(ValidationError):
        NeuronRegistryEntry(
            neuron_name="",
            display_name="Bad",
            category="system",
            description="bad",
        )


def test_valid_statuses_are_enforced() -> None:
    with pytest.raises(ValidationError):
        NeuronHealth(neuron_name="market", runtime_status="GREEN", health_status="ACTIVE")  # type: ignore[arg-type]


def test_registry_contract_is_observational_only() -> None:
    item = NeuronRegistryEntry(
        neuron_name="risk",
        display_name="Risk Neuron",
        category="risk",
        description="observes risk status",
        expected_signal_types=[],
        producer_source="manual",
        default_status="PARTIAL",
    )
    payload = item.to_api_dict()
    forbidden = {"buy", "sell", "enter_trade", "exit_trade", "approved", "rejected", "order_id"}
    assert forbidden.isdisjoint(payload)
