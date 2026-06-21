from __future__ import annotations


class StrategyRoutingError(RuntimeError):
    """Base error for V2.12 strategy routing."""


class StrategyRoutingBlocked(StrategyRoutingError):
    """Raised when runtime state blocks strategy routing."""

