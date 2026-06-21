from __future__ import annotations

import pytest

from app.events.envelope import EventEnvelope
from app.events.types import EVENT_TYPE_DESCRIPTIONS, EventType, validate_event_type


REQUIRED_EVENT_TYPES = {
    "market.discovered",
    "market.snapshot.created",
    "orderbook.snapshot.created",
    "rules.snapshot.created",
    "news.event.created",
    "social.event.created",
    "whale.event.created",
    "signal.created",
    "opportunity.scored",
    "strategy.routed",
    "risk.approved",
    "risk.rejected",
    "order.intent.created",
    "order.created",
    "position.opened",
    "exit.intent.created",
    "trade.closed",
    "learning.updated",
    "runtime.cycle.started",
    "runtime.cycle.finished",
    "runtime.mode.changed",
    "runtime.service.health.updated",
    "event.dlq.created",
    "event.replay.requested",
}


def test_all_required_event_types_exist() -> None:
    assert REQUIRED_EVENT_TYPES.issubset({event_type.value for event_type in EventType})


def test_event_type_strings_are_stable() -> None:
    assert EventType.MARKET_SNAPSHOT_CREATED.value == "market.snapshot.created"
    assert EventType.RUNTIME_CYCLE_STARTED.value == "runtime.cycle.started"
    assert EventType.EVENT_REPLAY_REQUESTED.value == "event.replay.requested"


def test_every_event_type_is_documented() -> None:
    for event_type in EventType:
        assert EVENT_TYPE_DESCRIPTIONS[event_type.value]


def test_unknown_event_type_rejected() -> None:
    with pytest.raises(ValueError):
        validate_event_type("future.unapproved.event")

    with pytest.raises(ValueError):
        EventEnvelope(
            event_type="future.unapproved.event",
            source_service="test",
            payload={},
        )


def test_runtime_event_types_exist() -> None:
    assert validate_event_type("runtime.cycle.started") == "runtime.cycle.started"
    assert validate_event_type("runtime.cycle.finished") == "runtime.cycle.finished"
