from __future__ import annotations


class EventBusError(Exception):
    """Base error for V2.1 event bus failures."""


class EventValidationError(EventBusError):
    """Raised when an event envelope violates the V2.1 contract."""


class EventStoreError(EventBusError):
    """Raised when durable event persistence fails."""


class EventDispatchError(EventBusError):
    """Raised when dispatch cannot safely continue."""


class EventReplayDenied(EventBusError):
    """Raised when replay is blocked by safety policy."""
