from __future__ import annotations


class AIBrainError(RuntimeError):
    """Base error for the V2.3 Hybrid AI Brain."""


class AIBudgetDenied(AIBrainError):
    """Raised when the AI Budget Governor blocks a model call."""


class AICaseFileUnavailable(AIBrainError):
    """Raised when a market case file cannot be built from real data."""


class AIModelUnavailable(AIBrainError):
    """Raised when a requested local or cloud model is unavailable."""


class AIResponseParseError(AIBrainError):
    """Raised when a model response cannot be parsed as structured JSON."""
