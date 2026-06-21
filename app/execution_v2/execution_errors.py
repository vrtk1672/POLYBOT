from __future__ import annotations


class ExecutionBlocked(RuntimeError):
    """Raised when execution preconditions block an internal paper/shadow action."""

