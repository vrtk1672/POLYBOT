from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.neural_mesh.impact_graph import EventEntity, ImpactLink, PositionThesisProfile


def test_create_valid_event_entity() -> None:
    entity = EventEntity(entity_type="person", entity_name="Satoshi Nakamoto", confidence=0.7)

    assert entity.entity_id.startswith("entity_")
    assert entity.entity_type == "person"
    assert entity.entity_name == "Satoshi Nakamoto"


def test_reject_empty_entity_name() -> None:
    with pytest.raises(ValidationError):
        EventEntity(entity_type="topic", entity_name="  ")


def test_create_valid_position_thesis_profile() -> None:
    thesis = PositionThesisProfile(position_id="position-1", market_id="market-1", entry_thesis="Neutral thesis record.")

    assert thesis.thesis_id.startswith("thesis_")
    assert thesis.position_id == "position-1"


def test_create_valid_impact_link() -> None:
    link = ImpactLink(
        signal_id="signal-1",
        market_id="market-1",
        impact_scope="market",
        impact_direction="neutral",
        impact_status="suggested",
        cortex_action_hint="WATCH",
        confidence=0.5,
        impact_strength=0.4,
        urgency=0.2,
    )

    assert link.impact_link_id.startswith("impact_")
    assert link.cortex_action_hint == "WATCH"


def test_reject_impact_link_without_subject() -> None:
    with pytest.raises(ValidationError):
        ImpactLink(market_id="market-1", impact_scope="market", cortex_action_hint="WATCH")


def test_reject_impact_link_without_target() -> None:
    with pytest.raises(ValidationError):
        ImpactLink(signal_id="signal-1", impact_scope="market", cortex_action_hint="WATCH")


def test_reject_invalid_impact_numeric_ranges() -> None:
    with pytest.raises(ValidationError):
        ImpactLink(signal_id="signal-1", market_id="market-1", impact_scope="market", confidence=1.5)
    with pytest.raises(ValidationError):
        ImpactLink(signal_id="signal-1", market_id="market-1", impact_scope="market", impact_strength=-0.1)
    with pytest.raises(ValidationError):
        ImpactLink(signal_id="signal-1", market_id="market-1", impact_scope="market", urgency=2)


def test_reject_executable_action_hints() -> None:
    for hint in ["BUY", "SELL", "PLACE_ORDER", "CANCEL_ORDER", "EXECUTE", "LIVE_APPROVED"]:
        with pytest.raises(ValidationError):
            ImpactLink(signal_id="signal-1", market_id="market-1", impact_scope="market", cortex_action_hint=hint)
